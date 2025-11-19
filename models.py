from sqlalchemy import Column, Integer, String, ForeignKey, Date, Float
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

    # se quiser guardar odds (se existirem na planilha)
    home_odds = Column(Float, nullable=True)
    draw_odds = Column(Float, nullable=True)
    away_odds = Column(Float, nullable=True)
