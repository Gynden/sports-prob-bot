from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Sport(Base):
    __tablename__ = "sports"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # ex: "soccer", "basketball", "esports"


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)              # ex: "Brasileirão Série A"
    country = Column(String, index=True, nullable=True)
    sport_id = Column(Integer, ForeignKey("sports.id"))

    sport = relationship("Sport", backref="leagues")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)              # ex: "Flamengo"
    sport_id = Column(Integer, ForeignKey("sports.id"))

    sport = relationship("Sport", backref="teams")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)  # id que vem da API externa
    league_id = Column(Integer, ForeignKey("leagues.id"))
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    kickoff = Column(DateTime)  # data/hora do jogo

    league = relationship("League", backref="matches")
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
