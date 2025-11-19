import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# No Render vamos usar a env DATABASE_URL (Postgres)
# Localmente, se não tiver, ele usa um SQLite só pra teste
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# Ajuste necessário porque o Render às vezes manda 'postgres://' em vez de 'postgresql://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
