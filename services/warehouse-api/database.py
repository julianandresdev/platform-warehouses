import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# SQL en los logs solo si se pide (SQL_ECHO=true); apagado por defecto
# para no ensuciar los logs ni afectar las pruebas de carga.
SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"

# Pool de conexiones. FastAPI atiende los endpoints síncronos en un pool de 40 hilos;
# con menos conexiones que hilos (el default de SQLAlchemy es 5 + 10) los hilos esperan
# una conexión y la limpieza que la liberaría no consigue hilo: la API se atasca hasta
# el timeout de 30 s (visto en la prueba de carga de J-06 sin caché).
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))

engine = create_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# El esquema NO se crea desde Python: la fuente de verdad es
# infrastructure/sql/warehouse/schema.sql (ver ADR-0003).
