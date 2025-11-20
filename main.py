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

# CORS para permitir chamadas do seu front (Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # se quiser, depois troca por ["https://bot-sports-analyst2.onrender.com"]
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
        "status": status.get("short"),      # ex: '1H', 'HT', '2H'
        "minute": status.get("elapsed"),     # minuto de jogo
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
# HELPERS DE ANÁLISE AO VIVO
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

    # quão avançado está o jogo (0 a 1)
    time_factor = max(0.0, min(1.0, minute / 90.0))

    # Ajuste básico pelo placar
    if diff > 0:
        # casa na frente
        bonus = 0.25 * diff * time_factor
        home_p += bonus
        away_p -= bonus * 0.6
        draw_p -= bonus * 0.4
    elif diff < 0:
        # fora na frente
        diff_abs = abs(diff)
        bonus = 0.25 * diff_abs * time_factor
        away_p += bonus
        home_p -= bonus * 0.6
        draw_p -= bonus * 0.4
    else:
        # empate no placar
        if minute >= 60:
            draw_p += 0.10 * time_factor
            home_p -= 0.05 * time_factor
            away_p -= 0.05 * time_factor

    # corrige valores negativos
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
# ENDPOINTS BÁSICOS (histórico)
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
    try:
        result = analyze_match(db, req.home_team, req.away_team, req.last_matches)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return result


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
# 1) LISTA DE JOGOS AO VIVO – BRASILEIRÃO SÉRIE A
# -----------------------------------------------------------------------------

@app.get("/live/bra")
async def live_bra():
    """
    Retorna os jogos ao vivo do Brasileirão Série A,
    filtrando a partir de TODOS os jogos ao vivo da API-FOOTBALL.
    """
    if not FOOTBALL_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="FOOTBALL_API_KEY (ou API_FOOTBALL_KEY) não configurada no ambiente do Render."
        )

    url = f"{FOOTBALL_API_BASE.rstrip('/')}/fixtures"
    # pede TODOS os jogos ao vivo do mundo
    params = {
        "live": "all",
    }
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params, headers=headers)

    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar API-FOOTBALL: {r.status_code} - {r.text}",
        )

    data = r.json()
    all_live = data.get("response", [])

    jogos_bra_serie_a = []

    for item in all_live:
        league = item.get("league", {}) or {}
        fixture = item.get("fixture", {}) or {}
        teams = item.get("teams", {}) or {}
        goals = item.get("goals", {}) or {}

        country = (league.get("country") or "").lower()
        league_name = (league.get("name") or "").lower()

        # filtra só Brasil + Série A
        if country != "brazil":
            continue
        if "serie a" not in league_name:
            continue

        jogos_bra_serie_a.append({
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date"),
            "status": fixture.get("status", {}).get("short"),
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
