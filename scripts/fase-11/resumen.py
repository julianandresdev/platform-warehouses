#!/usr/bin/env python3
"""Resume los CSV de Locust y los `docker stats` de docs/evidencias/fase-11/ en resumen.md (J-09)."""

import csv
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2] / "docs" / "evidencias" / "fase-11"
ORDEN = ["redis-off", "redis-on", "wh002-1-instancia", "wh002-3-instancias", "multibodega",
         "rampa-100", "rampa-500", "rampa-1000", "rampa-5000"]


def agregado(archivo: Path) -> dict | None:
    for fila in csv.DictReader(archivo.open(encoding="utf-8")):
        if fila["Name"] == "Aggregated":
            return fila
    return None


def cpu_de(stats: Path, patron: str) -> str:
    if not stats.exists():
        return "—"
    for linea in stats.read_text(encoding="utf-8").splitlines():
        partes = re.split(r"\s{2,}", linea.strip())
        if partes and re.search(patron, partes[0]):
            return partes[1]
    return "—"


def tabla(base: Path) -> list[str]:
    filas = ["| Escenario | Corrida | Requests | Fallos | Req/s | Prom. (ms) | P50 | P95 | P99 | CPU Locust |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for escenario in ORDEN:
        carpeta = base / escenario
        for archivo in sorted(carpeta.glob("*_stats.csv")) if carpeta.exists() else []:
            a = agregado(archivo)
            if not a:
                continue
            nombre = archivo.name[: -len("_stats.csv")]
            cpu = cpu_de(carpeta / "docker-stats.txt", rf"locust-{re.escape(nombre)}$")
            filas.append(
                f"| {escenario} | {nombre} | {a['Request Count']} | {a['Failure Count']} | "
                f"{float(a['Requests/s']):.1f} | {float(a['Average Response Time']):.1f} | "
                f"{a['50%']} | {a['95%']} | {a['99%']} | {cpu} |"
            )
    return filas


if __name__ == "__main__":
    salida = ["# Resumen de las corridas de carga (J-09)", "", *tabla(RAIZ)]
    antes = RAIZ / "sin-reinicio-entre-escenarios"
    if antes.exists():
        salida += ["", "## Sin reiniciar las réplicas entre escenarios (descartadas: miden el atasco)", "", *tabla(antes)]
    (RAIZ / "resumen.md").write_text("\n".join(salida) + "\n", encoding="utf-8")
    print("\n".join(salida))
