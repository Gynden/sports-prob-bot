from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Team, Match
from analysis import analyze_match
from ingest_bra_excel import ingest_bra
from live_service import fetch_live_matches_bra  # <-- novo import

# Cria as tabelas no banco (se ainda não existirem)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sports Probabilities API",
    version="1.0.0",
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
async def get_live_bra():
    """
    Retorna os jogos ao vivo do Brasileirão Série A,
    usando a API-FOOTBALL como fonte de dados em tempo real.
    """
    try:
        matches = await fetch_live_matches_bra()
        return {
            "count": len(matches),
            "matches": matches,
        }
    except HTTPException:
        # repassa erros HTTP que já vêm tratados do live_service
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")
