import asyncio
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from app import config
from app.api.fanout import query_fanout


class FanoutTests(unittest.IsolatedAsyncioTestCase):

    async def test_fanout(self):
        quantities = {
            "wh001": 103,
            "wh002": 23,
            "wh003": 58,
        }

        urls = ",".join(
            f"WH-00{i}=http://wh00{i}:8000"
            for i in range(1, 4)
        )

        scenario = "normal"

        async def handler(request):
            host = request.url.host

            if scenario == "missing":
                return httpx.Response(404)

            if scenario == "unavailable":
                return httpx.Response(503)

            if scenario == "partial" and host == "wh002":
                await asyncio.sleep(1)

            return httpx.Response(200, json={
                "warehouse_id": "WH-" + host[-3:],
                "quantity": quantities[host],
                "reserved_quantity": 0,
                "available_quantity": quantities[host],
                "version": 4,
                "updated_at": "2026-11-24T01:25:20Z",
            })

        with patch.object(config, "WAREHOUSE_URLS", urls):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:

                result = await query_fanout("P-001", client)
                self.assertEqual(result["total_quantity"], 184)
                self.assertFalse(result["partial"])

                scenario = "partial"
                result = await query_fanout("P-001", client)
                self.assertEqual(result["total_quantity"], 161)
                self.assertTrue(result["partial"])
                self.assertEqual(result["unavailable"], ["WH-002"])

                scenario = "missing"
                with self.assertRaises(HTTPException) as error:
                    await query_fanout("P-001", client)
                self.assertEqual(error.exception.status_code, 404)

                scenario = "unavailable"
                with self.assertRaises(HTTPException) as error:
                    await query_fanout("P-001", client)
                self.assertEqual(error.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
