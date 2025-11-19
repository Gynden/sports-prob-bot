from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey, Date, Float, DateTime
from sqlalchemy.orm import relationship

from database import Base


class Sport(Base):
    __tablename__ = "sports"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)

    leagues = relationship("League", back_populates="sport")


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    country = Column(String, index=True)

    sport_id = Column(Integer, ForeignKey("sports.id"))
    sport = relationship("Sport", back_populates="leagues")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)

    league = Column(String, index=True)     # Div
    season = Column(String, index=True)     # ex: 2025

    date = Column(Date, index=True)

    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))

    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])

    home_goals = Column(Integer)
    away_goals = Column(Integer)

    # resultado de 1X2
    result = Column(String, index=True)     # 'H', 'D', 'A'

    # odds (se existirem na planilha)
    home_odds = Column(Float, nullable=True)
    draw_odds = Column(Float, nullable=True)
    away_odds = Column(Float, nullable=True)


class LiveSnapshot(Base):
    """
    Snapshot de jogos ao vivo (estado atual do jogo em um momento do tempo).
    Cada chamada do /live/bra registra uma linha aqui.
    """
    __tablename__ = "live_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    fixture_id = Column(Integer, index=True, nullable=True)
    league = Column(String, nullable=True)
    season = Column(String, nullable=True)
    round = Column(String, nullable=True)

    date = Column(DateTime, nullable=True)

    status_short = Column(String, nullable=True)  # 1H, 2H, HT, FT...
    status_long = Column(String, nullable=True)
    minute = Column(Integer, nullable=True)

    home_team = Column(String, index=True, nullable=True)
    away_team = Column(String, index=True, nullable=True)
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
