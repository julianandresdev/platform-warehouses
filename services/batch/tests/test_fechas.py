
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


class PruebasFechas(unittest.TestCase):

    def test_movimiento_utc_corresponde_dia_anterior(self):
        movimiento = datetime(
            2026, 11, 23, 2, 0,
            tzinfo=ZoneInfo("UTC")
        )

        fecha_colombia = movimiento.astimezone(
            ZoneInfo("America/Bogota")
        ).date()

        self.assertEqual(
            fecha_colombia,
            date(2026, 11, 22)
        )

    def test_inicio_dia_colombia_en_utc(self):
        fecha = date(2026, 11, 22)

        inicio_colombia = datetime.combine(
            fecha,
            time.min,
            tzinfo=ZoneInfo("America/Bogota"),
        )

        inicio_utc = inicio_colombia.astimezone(
            ZoneInfo("UTC")
        )

        self.assertEqual(
            inicio_utc.hour,
            5
        )

    
    def test_final_dia_colombia_en_utc(self):
        fecha = date(2026, 11, 22)

        fin_colombia = datetime.combine(
            fecha + timedelta(days=1),
            time.min,
            tzinfo=ZoneInfo("America/Bogota"),
        )

        fin_utc = fin_colombia.astimezone(
            ZoneInfo("UTC")
        )

        self.assertEqual(
            fin_utc,
            datetime(
                2026, 11, 23, 5, 0,
                tzinfo=ZoneInfo("UTC")
            )
        )



if __name__ == "__main__":
    unittest.main()
