from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from models import Team, Match


def get_last_matches(db: Session, team_id: int, n: int = 10):
    """
    Retorna os últimos N jogos de um time (casa ou fora).
    """
    q = (
        db.query(Match)
        .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
        .order_by(desc(Match.date))
        .limit(n)
    )
    return q.all()


def compute_team_stats(matches, team_id: int):
    """
    Calcula média de gols marcados, sofridos e % de over 2.5 para um time.
    """
    if not matches:
        return None

    total = 0
    goals_for = 0
    goals_against = 0
    over25 = 0

    for m in matches:
        if m.home_team_id == team_id:
            gf = m.home_goals
            ga = m.away_goals
        else:
            gf = m.away_goals
            ga = m.home_goals

        if gf is None or ga is None:
            continue

        total += 1
        goals_for += gf
        goals_against += ga

        if gf + ga >= 3:
            over25 += 1

    if total == 0:
        return None

    return {
        "matches": total,
        "avg_goals_for": goals_for / total,
        "avg_goals_against": goals_against / total,
        "over25_percent": round(100 * over25 / total, 2),
    }


def analyze_match(db: Session, home_team_name: str, away_team_name: str, last_n: int = 10):
    """
    Analisa um confronto usando os últimos N jogos de cada time
    e devolve estatísticas básicas e uma probabilidade simples de over 2.5.
    """
    home = db.query(Team).filter(Team.name == home_team_name).first()
    away = db.query(Team).filter(Team.name == away_team_name).first()

    if not home or not away:
        raise ValueError("Um dos times não foi encontrado no banco.")

    home_matches = get_last_matches(db, home.id, last_n)
    away_matches = get_last_matches(db, away.id, last_n)

    home_stats = compute_team_stats(home_matches, home.id)
    away_stats = compute_team_stats(away_matches, away.id)

    if not home_stats or not away_stats:
        return {
            "home_team": home_team_name,
            "away_team": away_team_name,
            "message": "Poucos jogos com dados válidos para análise.",
        }

    over25_prob = (home_stats["over25_percent"] + away_stats["over25_percent"]) / 2

    return {
        "home_team": home_team_name,
        "away_team": away_team_name,
        "last_n": last_n,
        "home_stats": home_stats,
        "away_stats": away_stats,
        "over25_probability_percent": round(over25_prob, 2),
    }
