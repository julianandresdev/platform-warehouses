PRODUCT = {
    "sku": "E02-P001",
    "name": "Laptop",
    "description": "Producto de prueba",
    "category": "Tecnologia",
    "unit": "unidad"
}


def test_authentication(f1_client):
    response = f1_client.get(
        "/products",
        headers={"X-API-Key": ""}
    )

    assert response.status_code == 401

    response = f1_client.get(
        "/products",
        headers={"X-API-Key": "invalid-key"}
    )

    assert response.status_code == 401


def test_product_crud(f1_client):
    # CREATE
    response = f1_client.post(
        "/products",
        json=PRODUCT
    )

    assert response.status_code == 201

    product_id = response.json()["id"]

    # READ: listado
    response = f1_client.get("/products")

    assert response.status_code == 200
    assert len(response.json()) == 1

    # READ: producto individual
    response = f1_client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200
    assert response.json()["sku"] == PRODUCT["sku"]

    # UPDATE
    response = f1_client.put(
        f"/products/{product_id}",
        json={"name": "Laptop actualizada"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Laptop actualizada"

    response = f1_client.get(f"/products/{product_id}")
    assert response.json()["name"] == "Laptop actualizada"

    # DELETE
    response = f1_client.delete(
        f"/products/{product_id}"
    )

    assert response.status_code == 204

    # Verificar que ya no existe
    response = f1_client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 404


def test_duplicate_sku(f1_client):
    first = f1_client.post("/products", json=PRODUCT)
    second = f1_client.post("/products", json=PRODUCT)

    assert first.status_code == 201
    assert second.status_code == 409

    products = f1_client.get("/products").json()

    assert len(products) == 1


def test_delete_product_with_movements(f1_client):
    response = f1_client.post(
        "/products",
        json=PRODUCT
    )

    assert response.status_code == 201

    product_id = response.json()["id"]

    response = f1_client.post(
        "/inventory/movements",
        json={
            "sku": PRODUCT["sku"],
            "type": "RECEIPT",
            "quantity": 10
        }
    )

    assert response.status_code == 201

    response = f1_client.delete(
        f"/products/{product_id}"
    )

    assert response.status_code == 409

    response = f1_client.get(
        f"/products/{product_id}"
    )

    assert response.status_code == 200
