"""
Database Session — SQLAlchemy 2.0 Engine, SessionLocal, Base.

PostgreSQL only (UUID primary keys require native PG support).
Connection pool tuned for production: 20 connections + 10 overflow.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,       # reconnect on stale connections
    pool_recycle=3600,        # recycle connections every hour
    echo=False,               # set True to log SQL queries
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# All models import this Base so Alembic can discover them
Base = declarative_base()


def get_db():
    """
    FastAPI dependency — yields a DB session per request.
    Guarantees session is closed even on exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
