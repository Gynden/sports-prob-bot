from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Team, Match, LiveSnapshot
from analysis import analyze_match
from ingest_bra_excel import ingest_bra
from live_service import fetch_live_matches_bra

# Cria as tabelas no banco (incluindo LiveSnapshot)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sports Probabilities API",
    version="1.1.0",
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_fixture_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Converte a string de data da API-FOOTBALL para datetime.
    Se falhar, retorna None.
    """
    if not date_str:
        return None
    try:
        # normalmente vem no formato 2025-11-19T19:00:00+00:00
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def save_live_snapshots(db: Session, matches: List[Dict[str, Any]]) -> int:
    """
    Salva snapshots dos jogos ao vivo na tabela live_snapshots.
    Cada chamada registra o estado atual (placar, minuto, etc.).
    """
    saved = 0
    for m in matches:
        snap = LiveSnapshot(
            fixture_id=m.get("fixture_id"),
            league=m.get("league"),
            season=str(m.get("season") or ""),
            round=m.get("round"),
            date=parse_fixture_date(m.get("date")),
            status_short=m.get("status_short"),
            status_long=m.get("status_long"),
            minute=m.get("minute"),
            home_team=m.get("home_team"),
            away_team=m.get("away_team"),
            home_goals=m.get("home_goals"),
            away_goals=m.get("away_goals"),
        )
        db.add(snap)
        saved += 1

    if saved:
        db.commit()

    return saved


@app.get("/")
def root():
    return {"status": "ok", "message": "API de probabilidades esportivas no ar 🚀"}


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
    Calcula probabilidades e estatísticas para um confronto específico
    usando o histórico recente da BRA.xlsx já ingerida no banco.
    """
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


@app.get("/live/bra", summary="Jogos ao vivo do Brasileirão Série A")
async def get_live_bra(
    team: Optional[str] = Query(None, description="Filtrar por time (ex: Flamengo)"),
    db: Session = Depends(get_db),
):
    """
    Retorna os jogos ao vivo do Brasileirão Série A.
    - Se 'team' for informado, traz apenas jogos desse time.
    - Cada chamada salva um snapshot dos jogos no banco.
    """
    try:
        matches = await fetch_live_matches_bra(team=team)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")

    saved = save_live_snapshots(db, matches)

    return {
        "count": len(matches),
        "saved_snapshots": saved,
        "matches": matches,
    }


@app.get(
    "/live/bra/analyze",
    summary="Analisar um jogo ao vivo com base no histórico",
)
async def analyze_live_fixture(
    fixture_id: int = Query(..., description="ID da partida (fixture_id da API-FOOTBALL)"),
    last_matches: int = Query(10, ge=3, le=50),
    db: Session = Depends(get_db),
):
    """
    Combina dados AO VIVO + histórico:
    - Busca o fixture ao vivo pelo 'fixture_id'
    - Usa os nomes dos times para rodar analyze_match
    - Salva um snapshot desse jogo
    """
    # busca todos os jogos ao vivo e procura o fixture escolhido
    matches = await fetch_live_matches_bra(team=None)
    match = next((m for m in matches if m.get("fixture_id") == fixture_id), None)

    if not match:
        raise HTTPException(
            status_code=404,
            detail="Fixture ao vivo não encontrado para o Brasileirão Série A.",
        )

    home = match.get("home_team")
    away = match.get("away_team")

    if not home or not away:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível obter os nomes dos times para análise.",
        )

    # roda análise histórica usando seu motor atual
    try:
        analysis = analyze_match(db, home, away, last_matches)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # salva snapshot só desse jogo
    save_live_snapshots(db, [match])

    return {
        "fixture": match,
        "analysis": analysis,
    }
