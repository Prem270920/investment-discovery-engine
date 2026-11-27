"""
Database engine and session setup.

Central place where the DB connection lives. Everything else imports the session factory from here, 
so migrating SQLite -> Postgres later is a ONE-LINE change to DATABASE_URL. 
That's the payoff of using SQLAlchemy as an ORM rather than hand-writing sqlite3 calls.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.config import DATABASE_PATH

# The file's folder may not exist yet on a fresh server or a new volume.
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# The single knob to change for Postgres later
# DATABASE_URL = "postgresql+psycopg://user:pass@host:5432/investments"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

# Turn ON foreign-key enforcement for SQLite connections
@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Run 'PRAGMA foreign_keys=ON' on each new SQLite connection."""
   
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Session factory: call SessionLocal() to get a new session.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Base class our ORM models inherit from.
Base = declarative_base()