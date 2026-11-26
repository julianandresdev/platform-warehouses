import ast
import sqlite3
import unittest
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "services/central/app/workers/projection.py"
)

tree = ast.parse(SOURCE.read_text())

SQL = next(
    node.args[0].value
    for node in ast.walk(tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Name)
    and node.func.id == "text"
    and node.args
    and isinstance(node.args[0], ast.Constant)
    and isinstance(node.args[0].value, str)
    and "INSERT INTO global_inventory" in node.args[0].value
)


class TestProjectionVersion(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""
            CREATE TABLE global_inventory (
                sku TEXT,
                warehouse_id TEXT,
                quantity INTEGER,
                reserved_quantity INTEGER,
                version INTEGER,
                updated_at TEXT,
                PRIMARY KEY (sku, warehouse_id)
            )
        """)

    def save(self, version, quantity):
        self.db.execute(SQL, {
            "sku": "TEST-001",
            "warehouse_id": "WH-001",
            "quantity": quantity,
            "reserved_quantity": 0,
            "version": version,
            "occurred_at": "2026-11-23T22:00:00Z"
        })

    def current(self):
        return self.db.execute("""
            SELECT version, quantity
            FROM global_inventory
            WHERE sku = 'TEST-001'
        """).fetchone()

    def test_version_antigua_no_sobrescribe(self):
        self.save(2, 90)
        self.save(1, 999)
        self.assertEqual(self.current(), (2, 90))

    def test_version_nueva_actualiza(self):
        self.save(1, 90)
        self.save(2, 75)
        self.assertEqual(self.current(), (2, 75))

    def test_version_igual_no_sobrescribe(self):
        self.save(2, 75)
        self.save(2, 999)
        self.assertEqual(self.current(), (2, 75))


if __name__ == "__main__":
    unittest.main()
