import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def f1_engine():
    """Conexion exclusiva a PostgreSQL de pruebas."""

    database_url = os.getenv("E02_DATABASE_URL")

    if not database_url:
        pytest.skip("E02_DATABASE_URL no configurada")

    url = make_url(database_url)

    # Proteccion contra la eliminacion accidental de datos.
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "platform_test"
        or url.host not in ("127.0.0.1", "localhost")
        or url.port != 5542
    ):
        pytest.fail("Base de datos de pruebas no autorizada")

    engine = create_engine(database_url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            database = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()

            assert database == "platform_test"

        yield engine

    finally:
        engine.dispose()


@pytest.fixture
def clean_db(f1_engine):
    """Limpia las tablas antes y despues de cada prueba."""

    def reset():
        with f1_engine.begin() as connection:
            connection.execute(text("""
                TRUNCATE TABLE
                    inventory_movements,
                    inventory,
                    products,
                    outbox
                RESTART IDENTITY CASCADE
            """))

    reset()

    try:
        yield f1_engine
    finally:
        reset()


@pytest.fixture
def f1_client(clean_db, monkeypatch):
    """Cliente HTTP de FastAPI conectado a PostgreSQL real."""

    monkeypatch.setenv(
        "DATABASE_URL", os.environ["E02_DATABASE_URL"]
    )

    import config
    from app import app
    from database import get_db

    monkeypatch.setattr(config, "API_KEY", "e02-test-key")
    monkeypatch.setattr(config, "WAREHOUSE_ID", "WH-001")
    monkeypatch.setattr(config, "CACHE_ENABLED", False)

    TestingSession = sessionmaker(
        bind=clean_db,
        autoflush=False
    )

    def override_get_db():
        db = TestingSession()

        try:
            yield db
        finally:
            db.close()

    monkeypatch.setitem(
        app.dependency_overrides,
        get_db,
        override_get_db
    )

    with TestClient(
        app,
        headers={"X-API-Key": "e02-test-key"}
    ) as client:
        yield client
