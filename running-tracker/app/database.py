import os

# Load .env if present (for deploy env vars)
try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env from project root
except ImportError:
    pass

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_DIR = os.environ.get("REMOTE_DB_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
os.makedirs(DB_DIR, exist_ok=True)

DATABASE_URL = os.environ.get(
    "REMOTE_DATABASE_URL",
    f"sqlite:///{os.path.join(DB_DIR, 'tracker.db')}"
)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 — импортируем модели, чтобы они знали о Table
    Base.metadata.create_all(bind=engine)
