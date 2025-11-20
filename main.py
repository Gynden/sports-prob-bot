import os
from typing import Dict, Any

import requests
import httpx
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Team, Match
from analysis import analyze_match
from ingest_bra_excel import ingest_bra  # ingestão da BRA.xlsx

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO GERAL
# -----------------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

app = FastAPI(title="BRA Probabilities API")

# CORS – depois você pode restringir para o domínio do seu front
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ex.: ["https://seu-site.onrender.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FOOTBALL_API_BASE = os.getenv("FOOTBALL_API_BASE", "https://v3.football.api-sports.io")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")

# ID oficial do Brasileirão Série A na API-FOOTBALL
BR_SERIE_A_LEAGUE_ID = 71
BR_CURRENT_SEASON = 2025  # ajuste se necessário


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------------------------------
# NORMALIZAÇÃO DE NOMES DE TIME
# -----------------------------------------------------------------------------

# Aqui entram só casos onde a API-Football usa um nome diferente da BRA.xlsx.
TEAM_SYNONYMS: Dict[str, str] = {
    # Exemplo real: na base "Flamengo RJ", na API só "Flamengo"
    "flamengo": "Flamengo RJ",
    # depois você pode ir completando:
    # "cuiaba": "Cuiabá EC",
    # "atletico mg": "Atlético Mineiro",
    # etc.
}


def normalize_team_name(name: str, db: Session) -> str:
    """
    Converte o nome vindo do front/API para o nome que existe no banco/BRA.xlsx.

    Regra:
    1) Tenta bater exato com o que existe na tabela Team.
    2) Tenta começar/contain (resolve "Flamengo" x "Flamengo RJ").
    3) Só se nada bater usa TEAM_SYNONYMS.
    """
    if not name:
        return name

    key = name.strip().lower()

    # 1) Igualdade exata
    teams = db.query(Team).all()
    for t in teams:
        if t.name.strip().lower() == key:
            return t.name

    # 2) Começa com / contém
    for t in teams:
        tname = t.name.strip().lower()
        if tname.startswith(key) or key.startswith(tname):
            return t.name

    # 3) Sinônimos manuais
    if key in TEAM_SYNONYMS:
        return TEAM_SYNONYMS[key]

    # 4) Nada bateu
    return name


def _pick_first(d: dict, *keys):
    """
    Helper para achar a primeira chave existente e não-nula dentro de um dict.
    """
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


# -----------------------------------------------------------------------------
# HELPERS API-FOOTBALL
# -----------------------------------------------------------------------------

def _check_football_key():
    if not FOOTBALL_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="FOOTBALL_API_KEY não configurada no ambiente do Render.",
        )


def call_football_api(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Chamada genérica para a API-FOOTBALL.
    """
    _check_football_key()

    url = FOOTBALL_API_BASE.rstrip("/") + path
    headers = {"x-apisports-key": FOOTBALL_API_KEY}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro ao chamar API-FOOTBALL: {e}")

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Resposta inválida da API-FOOTBALL")

    if resp.status_code != 200:
        msg = data.get("message") or data
        raise HTTPException(
            status_code=502,
            detail=f"Erro da API-FOOTBALL (status {resp.status_code}): {msg}",
        )

    return data


def map_fixture_to_simple(f: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converte o objeto de fixture da API-FOOTBALL num formato simples.
    """
    fixture = f.get("fixture", {})
    league = f.get("league", {})
    teams = f.get("teams", {})
    goals = f.get("goals", {})

    status = fixture.get("status", {})
    return {
        "fixture_id": fixture.get("id"),
        "date": fixture.get("date"),
        "status": status.get("short"),      # ex: '1H', 'HT', '2H', 'FT'
        "minute": status.get("elapsed"),    # minuto de jogo
        "league": league.get("name"),
        "round": league.get("round"),
        "country": league.get("country"),
        "home_team": teams.get("home", {}).get("name"),
        "away_team": teams.get("away", {}).get("name"),
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
    }


def fetch_live_bra_fixtures() -> Dict[str, Any]:
    """
    Busca todos os jogos AO VIVO do Brasileirão Série A.
    (Não usado diretamente pelo front, mas deixei aqui caso queira.)
    """
    data = call_football_api(
        "/fixtures",
        params={
            "live": "all",
            "league": BR_SERIE_A_LEAGUE_ID,
            "season": BR_CURRENT_SEASON,
            "timezone": "America/Sao_Paulo",
        },
    )

    fixtures = data.get("response", []) or []
    mapped = [map_fixture_to_simple(f) for f in fixtures]

    return {
        "raw_count": len(fixtures),
        "count": len(mapped),
        "matches": mapped,
    }


def fetch_fixture_by_id(fixture_id: int) -> Dict[str, Any]:
    """
    Busca um fixture específico na API-FOOTBALL.
    """
    data = call_football_api(
        "/fixtures",
        params={"id": fixture_id, "timezone": "America/Sao_Paulo"},
    )

    fixtures = data.get("response", []) or []
    if not fixtures:
        raise HTTPException(status_code=404, detail="Jogo não encontrado na API-FOOTBALL.")

    return map_fixture_to_simple(fixtures[0])


# -----------------------------------------------------------------------------
# AJUSTE DE PROBABILIDADE AO VIVO (opcional para futuro)
# -----------------------------------------------------------------------------

def adjust_probabilities_with_live(
    hist_probs: Dict[str, float],
    live: Dict[str, Any],
) -> Dict[str, float]:
    """
    Ajusta as probabilidades pré-jogo (históricas) usando o placar ao vivo.
    Espera hist_probs no formato:
      {
        "home_win": 0.55,
        "draw": 0.25,
        "away_win": 0.20
      }
    """
    home_p = float(hist_probs.get("home_win", 0.33))
    draw_p = float(hist_probs.get("draw", 0.33))
    away_p = float(hist_probs.get("away_win", 0.33))

    minute = live.get("minute") or 0
    home_g = live.get("home_goals") or 0
    away_g = live.get("away_goals") or 0
    diff = home_g - away_g

    time_factor = max(0.0, min(1.0, minute / 90.0))  # 0 a 1

    if diff > 0:
        bonus = 0.25 * diff * time_factor
        home_p += bonus
        away_p -= bonus * 0.6
        draw_p -= bonus * 0.4
    elif diff < 0:
        diff_abs = abs(diff)
        bonus = 0.25 * diff_abs * time_factor
        away_p += bonus
        home_p -= bonus * 0.6
        draw_p -= bonus * 0.4
    else:
        if minute >= 60:
            draw_p += 0.10 * time_factor
            home_p -= 0.05 * time_factor
            away_p -= 0.05 * time_factor

    home_p = max(0.0, home_p)
    draw_p = max(0.0, draw_p)
    away_p = max(0.0, away_p)

    total = home_p + draw_p + away_p
    if total <= 0:
        home_p = draw_p = away_p = 1 / 3
        total = 1.0

    return {
        "home_win": home_p / total,
        "draw": draw_p / total,
        "away_win": away_p / total,
    }


# -----------------------------------------------------------------------------
# ENDPOINTS BÁSICOS
# -----------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "message": "API BRA.xlsx + live no ar 🚀"}


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
    """
    Endpoint principal usado pelo front.

    - Normaliza nomes de times (resolve diferença API x BRA.xlsx)
    - Chama analyze_match
    - Padroniza a resposta:

      {
        "home_team": "...",
        "away_team": "...",
        "probabilities": {
          "home_win": ...,
          "draw": ...,
          "away_win": ...
        },
        "goals_avg": ...
      }
    """

    # 1) Normaliza nomes
    normalized_home = normalize_team_name(req.home_team, db)
    normalized_away = normalize_team_name(req.away_team, db)

    # 2) Roda análise
    try:
        raw = analyze_match(db, normalized_home, normalized_away, req.last_matches)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not isinstance(raw, dict):
        return raw

    # 3) Acha bloco de probabilidades (flexível com nomes)
    probs_raw = (
        raw.get("probabilities")
        or raw.get("probs")
        or raw.get("prob")
        or {}
    )

    if not isinstance(probs_raw, dict) or not probs_raw:
        # se não tiver bloco separado, usa o próprio raw como fonte
        probs_raw = raw

    home_win = _pick_first(
        probs_raw,
        "home_win", "home", "mandante",
        "prob_home", "prob_mandante",
        "p_home", "p_mandante",
    )
    draw = _pick_first(
        probs_raw,
        "draw", "empate",
        "prob_draw", "prob_empate",
        "p_draw",
    )
    away_win = _pick_first(
        probs_raw,
        "away_win", "away", "visitante",
        "prob_away", "prob_visitante",
        "p_away", "p_visitante",
    )

    goals_avg = (
        raw.get("goals_avg")
        or raw.get("avg_goals")
        or raw.get("media_gols")
        or raw.get("gols_medios")
    )

    response: Dict[str, Any] = {
        "home_team": normalized_home,
        "away_team": normalized_away,
        "probabilities": {
            "home_win": home_win,
            "draw": draw,
            "away_win": away_win,
        },
        "goals_avg": goals_avg,
    }

    if "stats" in raw:
        response["stats"] = raw["stats"]

    return response


@app.post("/admin/ingest-bra")
def admin_ingest_bra(db: Session = Depends(get_db)):
    """
    Endpoint admin para popular o banco com a BRA.xlsx.
    Só roda se ainda não houver partidas (pra evitar duplicar).
    """
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


# -----------------------------------------------------------------------------
# JOGOS AO VIVO – BRASILEIRÃO SÉRIE A
# -----------------------------------------------------------------------------

@app.get("/live/bra")
async def live_bra():
    """
    Retorna os jogos ao vivo do Brasileirão Série A
    a partir de TODOS os jogos ao vivo da API-FOOTBALL,
    filtrando apenas os status que realmente indicam jogo em andamento.
    """
    if not FOOTBALL_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="FOOTBALL_API_KEY (ou API_FOOTBALL_KEY) não configurada no ambiente do Render."
        )

    url = f"{FOOTBALL_API_BASE.rstrip('/')}/fixtures"
    params = {"live": "all"}  # todos os jogos ao vivo do mundo
    headers = {"x-apisports-key": FOOTBALL_API_KEY}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params, headers=headers)

    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar API-FOOTBALL: {r.status_code} - {r.text}",
        )

    data = r.json()
    all_live = data.get("response", []) or []

    jogos_bra_serie_a = []

    # status que consideramos "jogo rolando"
    LIVE_STATUS = {"1H", "HT", "2H", "ET", "P"}

    for item in all_live:
        league = item.get("league", {}) or {}
        fixture = item.get("fixture", {}) or {}
        teams = item.get("teams", {}) or {}
        goals = item.get("goals", {}) or {}

        country = (league.get("country") or "").lower()
        league_name = (league.get("name") or "").lower()
        status_short = (fixture.get("status", {}) or {}).get("short") or ""

        # só Brasil + Série A
        if country != "brazil":
            continue
        if "serie a" not in league_name:
            continue

        # garante que está realmente em andamento
        if status_short not in LIVE_STATUS:
            continue

        jogos_bra_serie_a.append({
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date"),
            "status": status_short,
            "minute": fixture.get("status", {}).get("elapsed"),
            "league": league.get("name"),
            "round": league.get("round"),
            "home_team": teams.get("home", {}).get("name"),
            "away_team": teams.get("away", {}).get("name"),
            "home_goals": goals.get("home"),
            "away_goals": goals.get("away"),
        })

    return {
        "raw_count": len(all_live),
        "count": len(jogos_bra_serie_a),
        "matches": jogos_bra_serie_a,
    }
