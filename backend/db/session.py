# backend/db/session.py
import os
import logging

from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv

# 🔁 Auto-load environment and models to register tables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), os.pardir, ".env"))
# Import modules so SQLModel metadata sees all table models
import backend.models.menu
import backend.models.order

log = logging.getLogger("cafe-db")

# ── Database URL ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:1234@localhost:5432/postgres",
)
if not DATABASE_URL:
    log.error("No DATABASE_URL set! Use .env or set environment variable.")
    raise RuntimeError("DATABASE_URL required")

engine = create_engine(
    DATABASE_URL,
    echo=False,     # set to True if you want to see generated SQL
    pool_size=10,
    max_overflow=20,
)

def init_db() -> None:
    """
    Ensures that all SQLModel tables are created before use.
    This MUST be called at least once (e.g. in main.py or seed.py).
    """
    SQLModel.metadata.create_all(engine)
    log.info("Tables created (if not existed)")

def SessionLocal() -> Session:
    """
    Context-managed database session factory:
      with SessionLocal() as sess:
          sess.add(...)
          sess.commit()
    """
    return Session(engine)
