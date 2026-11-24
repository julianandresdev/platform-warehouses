
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


RUTA_HANDLER = Path(__file__).resolve().parents[1] / "handler.py"

spec = importlib.util.spec_from_file_location(
    "lambda_handler_modulo",
    RUTA_HANDLER,
)
handler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handler)


def crear_reporte_valido():
    bodegas = {}

    for warehouse_id in ("WH-001", "WH-002", "WH-003"):
        bodegas[warehouse_id] = {
            "total_movements": 0,
            "entries": 0,
            "shipments": 0,
            "adjustments": 0,
            "net_change": 0,
            "movements": [],
        }

    bodegas["WH-002"] = {
        "total_movements": 1,
        "entries": 100,
        "shipments": 0,
        "adjustments": 0,
        "net_change": 100,
        "movements": [
            {
                "id": 1,
                "product_id": 1,
                "warehouse_id": "WH-002",
                "type": "RECEIPT",
                "quantity": 100,
                "reference": "CARGA-FASE-5",
                "created_at": "2026-11-22T03:35:31.402569",
            }
        ],
    }

    return {
        "report_type": "daily_inventory_movements",
        "report_date": "2026-11-22",
        "source": "s3_csv",
        "total_warehouses": 3,
        "total_movements": 1,
        "total_entries": 100,
        "total_shipments": 0,
        "total_adjustments": 0,
        "net_change": 100,
        "warehouses": bodegas,
    }


def crear_evento_s3():
    return {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": "bucket-prueba"
                    },
                    "object": {
                        "key": "exports/daily-movements-2026-11-22.json"
                    },
                },
            }
        ]
    }


class PruebasLambda(unittest.TestCase):

    def setUp(self):
        self.reporte = crear_reporte_valido()
        self.s3 = MagicMock()
        self.eventbridge = MagicMock()

        self.eventbridge.put_events.return_value = {
            "FailedEntryCount": 0,
            "Entries": [{"EventId": "evento-prueba"}],
        }

    def configurar_s3(self, contenido):
        self.s3.get_object.return_value = {
            "Body": MagicMock(
                read=lambda: contenido
            )
        }

    def ejecutar_lambda(self):
        def crear_cliente(servicio):
            if servicio == "s3":
                return self.s3

            if servicio == "events":
                return self.eventbridge

            raise ValueError(servicio)

        with patch.object(
            handler.boto3,
            "client",
            side_effect=crear_cliente,
        ):
            return handler.lambda_handler(
                crear_evento_s3(),
                None,
            )

    def test_reporte_valido(self):
        self.configurar_s3(
            json.dumps(self.reporte).encode("utf-8")
        )

        resultado = self.ejecutar_lambda()
        cuerpo = json.loads(resultado["body"])

        self.assertEqual(cuerpo["processed"], 1)
        self.assertEqual(cuerpo["rejected"], 0)

        self.eventbridge.put_events.assert_called_once()

        entrada = self.eventbridge.put_events.call_args.kwargs[
            "Entries"
        ][0]

        detalle = json.loads(entrada["Detail"])

        self.assertEqual(
            detalle["report_date"],
            "2026-11-22",
        )

        self.assertEqual(
            detalle["total_entries"],
            100,
        )

    def test_json_invalido(self):
        self.configurar_s3(b"{json-invalido")

        resultado = self.ejecutar_lambda()
        cuerpo = json.loads(resultado["body"])

        self.assertEqual(cuerpo["processed"], 0)
        self.assertEqual(cuerpo["rejected"], 1)

        self.eventbridge.put_events.assert_not_called()

    def test_totales_inconsistentes(self):
        self.reporte["total_entries"] = 999

        self.configurar_s3(
            json.dumps(self.reporte).encode("utf-8")
        )

        resultado = self.ejecutar_lambda()
        cuerpo = json.loads(resultado["body"])

        self.assertEqual(cuerpo["rejected"], 1)
        self.eventbridge.put_events.assert_not_called()

    def test_falta_bodega(self):
        del self.reporte["warehouses"]["WH-003"]

        self.configurar_s3(
            json.dumps(self.reporte).encode("utf-8")
        )

        resultado = self.ejecutar_lambda()
        cuerpo = json.loads(resultado["body"])

        self.assertEqual(cuerpo["rejected"], 1)
        self.eventbridge.put_events.assert_not_called()

    def test_error_eventbridge(self):
        self.configurar_s3(
            json.dumps(self.reporte).encode("utf-8")
        )

        self.eventbridge.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [{"ErrorCode": "InternalFailure"}],
        }

        with self.assertRaises(RuntimeError):
            self.ejecutar_lambda()


if __name__ == "__main__":
    unittest.main()
