-- Datos de prueba de WH-002: mismo catalogo en todas las bodegas, stock distinto.
-- Cada stock inicial queda registrado como un RECEIPT con referencia SEED.

BEGIN;
INSERT INTO products (sku, name, category, unit) VALUES
    ('P-001', 'Caja de carton 40x30',     'Empaque',     'unidad'),
    ('P-002', 'Cinta de embalaje',        'Empaque',     'rollo'),
    ('P-003', 'Pallet de madera',         'Logistica',   'unidad'),
    ('P-004', 'Guantes de seguridad',     'Seguridad',   'par'),
    ('P-005', 'Casco industrial',         'Seguridad',   'unidad'),
    ('P-006', 'Etiquetas termicas',       'Papeleria',   'rollo'),
    ('P-007', 'Zuncho plastico',          'Empaque',     'rollo'),
    ('P-008', 'Carretilla manual',        'Logistica',   'unidad'),
    ('P-009', 'Lector de codigo de barras','Tecnologia', 'unidad'),
    ('P-010', 'Bascula digital',          'Tecnologia',  'unidad');

CREATE TEMP TABLE seed_stock (sku VARCHAR(100), quantity INTEGER) ON COMMIT DROP;
INSERT INTO seed_stock (sku, quantity) VALUES
    ('P-001', 20),
    ('P-002', 120),
    ('P-003', 10),
    ('P-004', 50),
    ('P-005', 30),
    ('P-006', 40),
    ('P-007', 200),
    ('P-008', 5),
    ('P-009', 8),
    ('P-010', 4);

INSERT INTO inventory (product_id, warehouse_id, quantity, reserved_quantity, version)
SELECT p.id, 'WH-002', s.quantity, 0, 1
FROM products p JOIN seed_stock s ON s.sku = p.sku;

INSERT INTO inventory_movements (product_id, warehouse_id, type, quantity, reference)
SELECT p.id, 'WH-002', 'RECEIPT', s.quantity, 'SEED'
FROM products p JOIN seed_stock s ON s.sku = p.sku;
COMMIT;
