from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import SessionLocal, Base, engine
from models import Sport, League
from api_sports import (
    get_soccer_leagues,
    ApiSportsError,
    search_soccer_team,
    get_head_to_head_fixtures,
    get_team_last_fixtures,
)

# Cria as tabelas no banco ao iniciar a API
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sports Probabilities API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {"status": "ok", "message": "API de probabilidades esportivas no ar 🚀"}


# --------- ESPORTES (SPORTS) --------- #

@app.post("/sports/init")
def init_sports(db: Session = Depends(get_db)):
    """
    Cria os esportes base no banco:
    - soccer
    - basketball
    - esports
    """
    default_sports = ["soccer", "basketball", "esports"]
    created = []

    for name in default_sports:
        existing = db.query(Sport).filter(Sport.name == name).first()
        if not existing:
            sport = Sport(name=name)
            db.add(sport)
            created.append(name)

    db.commit()

    return {"created": created, "message": "Esportes iniciais cadastrados com sucesso."}


@app.get("/sports")
def list_sports(db: Session = Depends(get_db)):
    """
    Lista todos os esportes cadastrados
    """
    sports = db.query(Sport).all()
    return [{"id": s.id, "name": s.name} for s in sports]


# --------- LIGAS (SOCCER) --------- #

@app.post("/ingest/soccer/leagues")
def ingest_soccer_leagues(country: str = "Brazil", db: Session = Depends(get_db)):
    """
    Busca ligas de futebol da API-SPORTS para um país
    e salva na tabela leagues.
    Exemplo de country: 'Brazil', 'England', etc.
    """
    soccer = db.query(Sport).filter(Sport.name == "soccer").first()
    if not soccer:
        raise HTTPException(status_code=400, detail="Sport 'soccer' não encontrado. Rode /sports/init primeiro.")

    try:
        data = get_soccer_leagues(country=country)
    except ApiSportsError as e:
        raise HTTPException(status_code=500, detail=str(e))

    response = data.get("response", [])
    created = []

    for item in response:
        league_info = item.get("league", {})
        country_info = item.get("country", {})

        league_name = league_info.get("name")
        league_country = country_info.get("name")

        if not league_name:
            continue

        existing = (
            db.query(League)
            .filter(League.name == league_name, League.country == league_country)
            .first()
        )
        if not existing:
            league = League(
                name=league_name,
                country=league_country,
                sport_id=soccer.id,
            )
            db.add(league)
            created.append(league_name)

    db.commit()

    return {
        "country_requested": country,
        "total_from_api": len(response),
        "created_in_db": created,
    }


@app.get("/leagues")
def list_leagues(db: Session = Depends(get_db)):
    """
    Lista todas as ligas cadastradas
    """
    leagues = db.query(League).all()
    return [
        {
            "id": l.id,
            "name": l.name,
            "country": l.country,
            "sport_id": l.sport_id,
        }
        for l in leagues
    ]


# --------- DEBUG: VER O QUE A API RETORNA PRO TIME --------- #

@app.get("/debug/soccer/search-team")
def debug_search_team(name: str, country: str | None = None):
    """
    Rota de debug para ver exatamente o que a API-SPORTS
    está retornando para um time.
    """
    try:
        data = search_soccer_team(name, country)
    except ApiSportsError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return data


# --------- PROBABILIDADE: OVER 2.5 GOLS (SOCCER) --------- #

class Over25Request(BaseModel):
    home_team: str = Field(..., description="Nome do time da casa (ex: Flamengo)")
    away_team: str = Field(..., description="Nome do time visitante (ex: Palmeiras)")
    country: str | None = Field(
        default=None,
        description="País dos times (opcional, ex: Brazil, England)"
    )
    last_matches: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Quantidade de jogos recentes para analisar"
    )


def _search_team_or_404(name: str, country: str | None):
    """
    Tenta buscar o time com país; se não achar nada e tiver país,
    tenta novamente sem país. Se mesmo assim não vier nada, lança 404.
    """
    try:
        data = search_soccer_team(name, country)
    except ApiSportsError as e:
        raise HTTPException(status_code=500, detail=str(e))

    resp = data.get("response", [])

    if not resp and country:
        try:
            data = search_soccer_team(name, None)
        except ApiSportsError as e:
            raise HTTPException(status_code=500, detail=str(e))
        resp = data.get("response", [])

    if not resp:
        raise HTTPException(status_code=404, detail=f"Time não encontrado: {name}")

    return resp[0].get("team", {})


def _analyze_over25_from_fixtures(fixtures: list[dict]) -> tuple[int, int, int]:
    """
    Recebe uma lista de fixtures (como vem da API) e conta:
    - jogos válidos
    - quantos bateram over 2.5
    - quantos ficaram em under ou igual
    """
    total_jogos_validos = 0
    over25_hits = 0
    under_or_equal_hits = 0

    for f in fixtures:
        goals = f.get("goals", {})
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        if home_goals is None or away_goals is None:
            continue  # ignora jogos sem placar definido

        total_gols = home_goals + away_goals
        total_jogos_validos += 1

        if total_gols >= 3:
            over25_hits += 1
        else:
            under_or_equal_hits += 1

    return total_jogos_validos, over25_hits, under_or_equal_hits


@app.post("/probabilities/soccer/over25")
def probability_over25(req: Over25Request):
    """
    Calcula a probabilidade de OVER 2.5 gols.
    Estratégia:
    1) Tenta usar confrontos diretos (H2H).
    2) Se não houver H2H suficiente, usa os últimos jogos de cada time
       separadamente (home + away) como amostra.
    """

    # 1) Buscar times com fallback
    home_team_info = _search_team_or_404(req.home_team, req.country)
    away_team_info = _search_team_or_404(req.away_team, req.country)

    home_id = home_team_info.get("id")
    away_id = away_team_info.get("id")

    if home_id is None or away_id is None:
        raise HTTPException(status_code=500, detail="Não foi possível obter os IDs dos times na API-Sports.")

    # ---------- TENTATIVA 1: H2H ---------- #
    try:
        h2h_data = get_head_to_head_fixtures(home_id, away_id, last=req.last_matches)
    except ApiSportsError as e:
        raise HTTPException(status_code=500, detail=str(e))

    h2h_fixtures = h2h_data.get("response", [])

    total_validos_h2h, over25_h2h, under_h2h = _analyze_over25_from_fixtures(h2h_fixtures)

    # Se tivermos pelo menos 1 jogo válido de H2H, usamos só H2H
    if total_validos_h2h > 0:
        prob_over25 = over25_h2h / total_validos_h2h
        prob_under_or_equal = under_h2h / total_validos_h2h

        return {
            "mode": "head_to_head",
            "home_team": {
                "id": home_id,
                "name": home_team_info.get("name"),
            },
            "away_team": {
                "id": away_id,
                "name": away_team_info.get("name"),
            },
            "matches_analyzed": total_validos_h2h,
            "over25_probability_percent": round(prob_over25 * 100, 2),
            "under25_or_equal_probability_percent": round(prob_under_or_equal * 100, 2),
            "details": {
                "over25_hits": over25_h2h,
                "under_or_equal_hits": under_h2h,
            },
        }

    # ---------- TENTATIVA 2: ÚLTIMOS JOGOS DE CADA TIME ---------- #
    try:
        home_last = get_team_last_fixtures(home_id, last=req.last_matches)
        away_last = get_team_last_fixtures(away_id, last=req.last_matches)
    except ApiSportsError as e:
        raise HTTPException(status_code=500, detail=str(e))

    home_fixtures = home_last.get("response", [])
    away_fixtures = away_last.get("response", [])

    # junta todos os jogos recentes dos dois times
    combined_fixtures = home_fixtures + away_fixtures

    total_validos_comb, over25_comb, under_comb = _analyze_over25_from_fixtures(combined_fixtures)

    if total_validos_comb == 0:
        raise HTTPException(
            status_code=400,
            detail="Não há jogos recentes com placar válido para analisar (H2H nem últimos jogos)."
        )

    prob_over25 = over25_comb / total_validos_comb
    prob_under_or_equal = under_comb / total_validos_comb

    return {
        "mode": "teams_recent_matches",
        "home_team": {
            "id": home_id,
            "name": home_team_info.get("name"),
        },
        "away_team": {
            "id": away_id,
            "name": away_team_info.get("name"),
        },
        "matches_analyzed": total_validos_comb,
        "over25_probability_percent": round(prob_over25 * 100, 2),
        "under25_or_equal_probability_percent": round(prob_under_equal * 100, 2),
        "details": {
            "over25_hits": over25_comb,
            "under_or_equal_hits": under_comb,
        },
    }
