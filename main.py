import os
import httpx
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Team, Match
from analysis import analyze_match
from ingest_bra_excel import ingest_bra

Base.metadata.create_all(bind=engine)

app = FastAPI(title="BRA Probabilities API")

# --- NOVO: chave da API de jogos ao vivo ---
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

if not API_FOOTBALL_KEY:
    print("[AVISO] API_FOOTBALL_KEY não configurada nas variáveis de ambiente. "
          "O endpoint /live/bra vai retornar erro 500.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {"status": "ok", "message": "API BRA.xlsx no ar 🚀"}


@app.get("/teams")
def list_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).order_by(Team.name).all()
    return [{"id": t.id, "name": t.name} for t in teams]


@app.get("/matches/count")
def matches_count(db: Session = Depends(get_db)):
    total = db.query(Match).count()
    return {"matches": total}


class BraMatchRequest(BaseModel):
    home_team: str = Field(..., example="Flamengo")
    away_team: str = Field(..., example="Fluminense")
    last_matches: int = Field(10, ge=3, le=50)


@app.post("/probabilities/bra/match")
def bra_match_probability(req: BraMatchRequest, db: Session = Depends(get_db)):
    try:
        result = analyze_match(db, req.home_team, req.away_team, req.last_matches)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return result


@app.post("/admin/ingest-bra")
def admin_ingest_bra(db: Session = Depends(get_db)):
    total_before = db.query(Match).count()
    if total_before > 0:
        return {
            "status": "skipped",
            "reason": "Banco já possui partidas. Não foi feita nova ingestão.",
            "matches": total_before,
        }

    try:
        inserted = ingest_bra()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na ingestão: {e}")

    total_after = db.query(Match).count()
    return {
        "status": "ok",
        "inserted": inserted,
        "matches": total_after,
    }

# -------------------------------------------------------------------
# NOVO ENDPOINT /live/bra – busca TODOS os jogos ao vivo e filtra Brasil Série A
# -------------------------------------------------------------------
@app.get("/live/bra")
async def live_bra():
    """
    Jogos ao vivo da Série A do Brasileirão.
    Busca todos os fixtures 'live' na API externa e filtra por:
      - country == 'Brazil'
      - league name contendo 'Serie A'
    """

    if not API_FOOTBALL_KEY:
        raise HTTPException(
            status_code=500,
            detail="API_FOOTBALL_KEY não configurada no ambiente do Render.",
        )

    url = "https://v3.football.api-sports.io/fixtures"
    params = {
        "live": "all",
        "timezone": "America/Sao_Paulo",
    }
    headers = {
        "x-apisports-key": API_FOOTBALL_KEY,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Erro na API de jogos ao vivo: {resp.text}",
        )

    data = resp.json()
    fixtures = data.get("response", [])

    matches = []
    for fx in fixtures:
        league = fx.get("league", {})
        country = league.get("country")
        league_name = league.get("name", "")

        # Filtra apenas Brasil Série A
        if country != "Brazil":
            continue
        if "Serie A" not in league_name:
            continue

        fixture = fx.get("fixture", {})
        teams = fx.get("teams", {})
        goals = fx.get("goals", {})

        matches.append({
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date"),
            "status": fixture.get("status", {}).get("short"),
            "league": league_name,
            "round": league.get("round"),
            "home_team": teams.get("home", {}).get("name"),
            "away_team": teams.get("away", {}).get("name"),
            "home_goals": goals.get("home"),
            "away_goals": goals.get("away"),
        })

    return {
        "count": len(matches),
        "matches": matches,
    }
