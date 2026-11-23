import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Dirección de conexión a PostgreSQL.
# Docker Compose proporcionará esta variable.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no está configurada")

# Motor encargado de administrar las conexiones.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)

# Fábrica de sesiones para consultar y modificar datos.
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# Dependencia que utilizarán los endpoints de FastAPI.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
