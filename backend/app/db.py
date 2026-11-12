import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")
DATA_DIR = Path(os.getenv("DIANOIA_DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
database_url = os.getenv("DIANOIA_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'dianoia.db').as_posix()}")
if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:////"):
    sqlite_path = Path(database_url.removeprefix("sqlite:///"))
    if not sqlite_path.is_absolute():
        sqlite_path = BASE_DIR / sqlite_path
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{sqlite_path.as_posix()}"

engine = create_engine(database_url, pool_pre_ping=True)
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")


class Base(DeclarativeBase):
    pass


def database():
    with Session(engine) as session:
        yield session
