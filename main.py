import os

import httpx
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Team, Match
from analysis import analyze_match
from ingest_bra_excel import ingest_bra  # ingestão da planilha BRA.xlsx

# --------------------------------------------------------------------
# DB
# --------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

app = FastAPI(title="BRA Probabilities API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --------------------------------------------------------------------
# Variáveis de ambiente para API-FOOTBALL
# --------------------------------------------------------------------
# aceita tanto FOOTBALL_API_KEY quanto API_FOOTBALL_KEY
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY") or os.getenv("API_FOOTBALL_KEY")
FOOTBALL_API_BASE = os.getenv(
    "FOOTBALL_API_BASE",
    "https://v3.football.api-sports.io"
)

# --------------------------------------------------------------------
# Rotas básicas / probabilidades
# --------------------------------------------------------------------
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


# --------------------------------------------------------------------
# Endpoint admin para ingestão da planilha BRA.xlsx
# --------------------------------------------------------------------
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


# --------------------------------------------------------------------
# Endpoint de jogos AO VIVO – Brasileirão Série A (API-FOOTBALL)
# --------------------------------------------------------------------
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
        # quantos jogos ao vivo o mundo todo tem
        "raw_count": len(all_live),
        # quantos a gente filtrou como Brasileirão Série A
        "count": len(jogos_bra_serie_a),
        "matches": jogos_bra_serie_a,
    }
