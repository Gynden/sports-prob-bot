from sqlalchemy import Column, Integer, String, ForeignKey
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
