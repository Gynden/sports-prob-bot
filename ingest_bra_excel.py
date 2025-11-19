import io
import pandas as pd
import requests
from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
from models import Team, Match

# URL correta da planilha .xlsx (não o link de visualização da Microsoft)
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


def _find_col(df: pd.DataFrame, options: list[str], logical_name: str) -> str:
    """
    Procura uma coluna dentro de várias opções.
    Ex.: ["HomeTeam", "Home"] para o time da casa.
    """
    for col in options:
        if col in df.columns:
            return col
    raise RuntimeError(f"Coluna obrigatória não encontrada na planilha ({logical_name}). "
                       f"Procuradas: {options}. Colunas existentes: {list(df.columns)}")


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
    # IMPORTANTE: engine=openpyxl para .xlsx
    df = pd.read_excel(file_bytes, engine="openpyxl")

    # Mapeia nomes lógicos -> nomes reais das colunas
    date_col = _find_col(df, ["Date"], "data")
    home_col = _find_col(df, ["HomeTeam", "Home"], "time da casa")
    away_col = _find_col(df, ["AwayTeam", "Away"], "time visitante")
    home_goals_col = _find_col(df, ["FTHG", "HG"], "gols da casa")
    away_goals_col = _find_col(df, ["FTAG", "AG"], "gols do visitante")
    result_col = _find_col(df, ["FTR", "Res"], "resultado (H/D/A)")
    league_col = None
    try:
        league_col = _find_col(df, ["Div", "League"], "liga")
    except RuntimeError:
        # se não tiver, vamos assumir "BRA"
        pass

    # odds 1X2 (podem não existir)
    home_odds_col = None
    draw_odds_col = None
    away_odds_col = None
    for opt in ["B365H", "PSCH"]:
        if opt in df.columns:
            home_odds_col = opt
            break

    for opt in ["B365D", "PSCD"]:
        if opt in df.columns:
            draw_odds_col = opt
            break

    for opt in ["B365A", "PSCA"]:
        if opt in df.columns:
            away_odds_col = opt
            break

    create_tables()
    db = SessionLocal()

    try:
        inserted = 0

        for _, row in df.iterrows():
            dt = pd.to_datetime(row[date_col], dayfirst=True, errors="coerce")
            if pd.isna(dt):
                continue

            home_name = str(row[home_col]).strip()
            away_name = str(row[away_col]).strip()
            if not home_name or not away_name:
                continue

            home_team = get_or_create_team(db, home_name)
            away_team = get_or_create_team(db, away_name)

            try:
                home_goals = int(row[home_goals_col])
                away_goals = int(row[away_goals_col])
            except Exception:
                continue

            result = str(row[result_col]).strip()  # H, D ou A

            league = str(row[league_col]) if league_col and pd.notna(row[league_col]) else "BRA"
            season = parse_season(row)

            def safe_float(col_name):
                if col_name and col_name in df.columns and pd.notna(row[col_name]):
                    try:
                        return float(row[col_name])
                    except Exception:
                        return None
                return None

            home_odds = safe_float(home_odds_col)
            draw_odds = safe_float(draw_odds_col)
            away_odds = safe_float(away_odds_col)

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
