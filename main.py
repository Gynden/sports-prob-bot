from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import SessionLocal, Base, engine

# Cria as tabelas no banco (MVP - depois podemos trocar por migrações)
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
