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
# Segundos que un request espera una conexión libre antes de fallar con 503. El valor por
# defecto de SQLAlchemy (30 s) deja a los hilos bloqueados medio minuto bajo sobrecarga.
DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "5"))

engine = create_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


async def get_db():
    """Sesión por request. Es ``async`` a propósito (J-06, atasco visto en J-09).

    FastAPI ejecuta la limpieza de una dependencia con ``yield`` síncrona en el pool de
    hilos. Si todos los hilos están ocupados por requests que esperan una conexión, el
    ``close()`` que la devolvería no consigue hilo: las conexiones quedan ``idle in
    transaction`` para siempre y la API no se recupera aunque cese la carga. Con la
    dependencia ``async`` el ``close()`` corre en el bucle de eventos, sin necesitar un
    hilo. ``SessionLocal()`` no abre conexión hasta el primer uso, y ``close()`` solo
    devuelve la conexión al pool (un ROLLBACK, sin esperas largas).
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# El esquema NO se crea desde Python: la fuente de verdad es
# infrastructure/sql/warehouse/schema.sql (ver ADR-0003).
