
import hashlib
import io
import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from main import validar_manifiesto


class S3Simulado:
    def __init__(self, objetos):
        self.objetos = objetos

    def get_object(self, Bucket, Key):
        if Key not in self.objetos:
            raise FileNotFoundError(Key)

        return {"Body": io.BytesIO(self.objetos[Key])}


class PruebasManifiesto(unittest.TestCase):
    def setUp(self):
        self.fecha = date(2026, 11, 22)
        self.prefijo = (
            "inputs/movements/daily/2026-11-22/"
        )

        self.objetos = {}
        bodegas = {}

        for warehouse_id in (
            "WH-001",
            "WH-002",
            "WH-003",
        ):
            clave = f"{self.prefijo}{warehouse_id}.csv"
            contenido = (
                "id,product_id,warehouse_id,type,"
                "quantity,reference,created_at\n"
            ).encode("utf-8")

            self.objetos[clave] = contenido

            bodegas[warehouse_id] = {
                "key": clave,
                "sha256": hashlib.sha256(
                    contenido
                ).hexdigest(),
            }

        self.manifiesto = {
            "report_date": self.fecha.isoformat(),
            "status": "COMPLETE",
            "warehouses": bodegas,
        }

        self.guardar_manifiesto()

    def guardar_manifiesto(self):
        clave = f"{self.prefijo}manifest.json"
        self.objetos[clave] = json.dumps(
            self.manifiesto
        ).encode("utf-8")

    def validar(self):
        validar_manifiesto(
            S3Simulado(self.objetos),
            "bucket-prueba",
            self.fecha,
        )

    def test_manifiesto_valido(self):
        self.validar()

    def test_manifiesto_incompleto(self):
        self.manifiesto["status"] = "INCOMPLETE"
        self.guardar_manifiesto()

        with self.assertRaises(ValueError):
            self.validar()

    def test_falta_una_bodega(self):
        del self.manifiesto["warehouses"]["WH-003"]
        self.guardar_manifiesto()

        with self.assertRaises(ValueError):
            self.validar()

    def test_csv_alterado(self):
        clave = f"{self.prefijo}WH-002.csv"
        self.objetos[clave] = b"contenido alterado"

        with self.assertRaises(ValueError):
            self.validar()

    def test_fecha_incorrecta(self):
        self.manifiesto["report_date"] = "2026-11-21"
        self.guardar_manifiesto()

        with self.assertRaises(ValueError):
            self.validar()


if __name__ == "__main__":
    unittest.main()
