from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from typing import List

from database import SessionLocal, Base, engine
from models import Sport

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
