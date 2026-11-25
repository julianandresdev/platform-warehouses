from sqlalchemy import text


def test_health(f1_client):
    response = f1_client.get("/health")

    assert response.status_code == 200


def test_database_ready(f1_client):
    response = f1_client.get("/health/ready")

    assert response.status_code == 200


def test_database_is_empty(clean_db):
    with clean_db.connect() as connection:
        for table in (
            "products",
            "inventory",
            "inventory_movements",
            "outbox"
        ):
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

            assert count == 0
