import io
import pandas as pd
import requests
from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
from models import Team, Match

# URL correta da planilha do Brasil no football-data.co.uk
BRA_XLSX_URL = "https://www.football-data.co.uk/new/BRA.xlsx"


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_or_create_team(db: Session, name: str) -> Team:
    team = db.query(Team).filter(Team.name == name).first()
    if not team:
        team = Team(name=name)
        db.add(team)
        db.commit()
        db.refresh(team)
    return team


def parse_season(row) -> str:
    """
    Tenta deduzir a Season.
    Se o arquivo tiver coluna 'Season', usa ela.
    Se não tiver, usa o ano da data.
    """
    if "Season" in row and pd.notna(row["Season"]):
        return str(row["Season"])

    if "Date" in row and pd.notna(row["Date"]):
        try:
            dt = pd.to_datetime(row["Date"], dayfirst=True, errors="coerce")
            if pd.notna(dt):
                return str(dt.year)
        except Exception:
            pass

    return "unknown"


def ingest_bra() -> int:
    """
    Baixa a BRA.xlsx, cria as tabelas (se preciso) e insere as partidas.
    Retorna a quantidade de jogos inseridos.
    """
    print("Baixando planilha BRA.xlsx...")
    resp = requests.get(BRA_XLSX_URL, timeout=60)
    resp.raise_for_status()

    file_bytes = io.BytesIO(resp.content)

    print("Lendo planilha com pandas...")
    # IMPORTANTE: usar engine="openpyxl"
    df = pd.read_excel(file_bytes, engine="openpyxl")

    # checa colunas obrigatórias
    for required in ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]:
        if required not in df.columns:
            raise RuntimeError(f"Coluna obrigatória não encontrada na planilha: {required}")

    create_tables()
    db = SessionLocal()

    try:
        inserted = 0

        for _, row in df.iterrows():
            dt = pd.to_datetime(row["Date"], dayfirst=True, errors="coerce")
            if pd.isna(dt):
                continue

            home_name = str(row["HomeTeam"]).strip()
            away_name = str(row["AwayTeam"]).strip()
            if not home_name or not away_name:
                continue

            home_team = get_or_create_team(db, home_name)
            away_team = get_or_create_team(db, away_name)

            try:
                home_goals = int(row["FTHG"])
                away_goals = int(row["FTAG"])
            except Exception:
                continue

            result = str(row["FTR"]).strip()  # H, D ou A

            league = str(row["Div"]) if "Div" in df.columns else "BRA"
            season = parse_season(row)

            home_odds = float(row["B365H"]) if "B365H" in df.columns and pd.notna(row["B365H"]) else None
            draw_odds = float(row["B365D"]) if "B365D" in df.columns and pd.notna(row["B365D"]) else None
            away_odds = float(row["B365A"]) if "B365A" in df.columns and pd.notna(row["B365A"]) else None

            match = Match(
                league=league,
                season=season,
                date=dt.date(),
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                home_goals=home_goals,
                away_goals=away_goals,
                result=result,
                home_odds=home_odds,
                draw_odds=draw_odds,
                away_odds=away_odds,
            )

            db.add(match)
            inserted += 1

            if inserted % 100 == 0:
                db.commit()
                print(f"{inserted} partidas inseridas...")

        db.commit()
        print(f"Ingestão concluída. Total de partidas inseridas: {inserted}")

        return inserted

    finally:
        db.close()


if __name__ == "__main__":
    # modo “script”, se algum dia você quiser rodar local
    total = ingest_bra()
    print("Total inserido:", total)
