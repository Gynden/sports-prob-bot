from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal, Base, engine
from models import Sport, League
from api_sports import get_soccer_leagues, ApiSportsError

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

        # Verifica se já existe liga com mesmo nome + país
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
