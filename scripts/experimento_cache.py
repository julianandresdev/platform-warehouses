#!/usr/bin/env python3
"""Experimento F2 (J-06): carga con y sin caché Redis y tabla comparativa.

Por cada modo (cache-on, cache-off) recrea la API con CACHE_ENABLED, lanza Locust
(100 usuarios, 2 min por defecto sobre el mismo SKU) y mide: RPS, P50/P95/P99,
CPU de api/db/redis (docker stats), transacciones en PostgreSQL
(diferencia de pg_stat_database.xact_commit) y tasa de hit (/metrics).

    python3 scripts/experimento_cache.py            # 100 usuarios, 2m
    LOAD_TIME=20s python3 scripts/experimento_cache.py   # prueba rápida

Deja los CSV de Locust y resumen.md en docs/evidencias/fase-2/.
"""

import csv
import os
import re
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# LOAD_TAG separa corridas distintas (p. ej. "saturacion"): CSV y resumen salen en una subcarpeta.
TAG = os.getenv("LOAD_TAG", "")
OUT = ROOT / "docs" / "evidencias" / "fase-2" / TAG
API = "http://localhost:8000"
USERS = os.getenv("LOAD_USERS", "100")
DURATION = os.getenv("LOAD_TIME", "2m")
ENDPOINT = "GET /inventory/{sku}"


def sh(*cmd, env=None, check=True):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd, cwd=ROOT, env=full_env, text=True, capture_output=True, check=check
    ).stdout.strip()


def container(service):
    return sh("docker", "compose", "ps", "-q", service)


def wait_healthy():
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{API}/health", timeout=2)
            return
        except Exception:
            time.sleep(1)
    raise SystemExit("la API no responde en /health")


def xact_commit():
    q = "select xact_commit from pg_stat_database where datname='platform'"
    return int(sh("docker", "compose", "exec", "-T", "db", "psql", "-U", "admin", "-d", "platform", "-tAc", q))


def metric(name):
    body = urllib.request.urlopen(f"{API}/metrics", timeout=5).read().decode()
    m = re.search(rf"^{name}(?:\{{[^}}]*\}})? ([0-9.e+]+)$", body, re.M)
    return float(m.group(1)) if m else 0.0


def sample_cpu(ids, stop, samples):
    while not stop.is_set():
        out = sh("docker", "stats", "--no-stream", "--format", "{{.ID}} {{.CPUPerc}}", check=False)
        for line in out.splitlines():
            cid, cpu = line.split()
            for name, full in ids.items():
                if full.startswith(cid):
                    samples[name].append(float(cpu.rstrip("%")))


def run_mode(name, cache_enabled):
    print(f"\n== {name} (CACHE_ENABLED={cache_enabled}) ==", flush=True)
    sh("docker", "compose", "up", "-d", "--force-recreate", "api", env={"CACHE_ENABLED": cache_enabled})
    wait_healthy()
    sh("docker", "compose", "exec", "-T", "redis", "redis-cli", "flushall")
    urllib.request.urlopen(urllib.request.Request(f"{API}/inventory/P-001", headers={"X-API-Key": "dev-api-key"}))

    ids = {s: container(s) for s in ("api", "db", "redis")}
    samples = {s: [] for s in ids}
    stop = threading.Event()
    sampler = threading.Thread(target=sample_cpu, args=(ids, stop, samples), daemon=True)

    hits0, misses0 = metric("cache_hits_total"), metric("cache_misses_total")
    x0 = xact_commit()
    sampler.start()
    sh(
        "docker", "compose", "--profile", "load", "run", "--rm", "locust",
        env={"LOAD_NAME": name, "LOAD_USERS": USERS, "LOAD_TIME": DURATION, "CACHE_ENABLED": cache_enabled},
        check=False,  # Locust sale con código 1 si hubo fallos; se reportan en la tabla
    )
    stop.set()
    sampler.join(timeout=10)
    x1 = xact_commit()
    hits, misses = metric("cache_hits_total") - hits0, metric("cache_misses_total") - misses0

    with open(OUT / f"{name}_stats.csv") as f:
        row = next(r for r in csv.DictReader(f) if r["Name"] == ENDPOINT)
    total = int(row["Request Count"])
    return {
        "modo": name,
        "peticiones": total,
        "fallos": int(row["Failure Count"]),
        "rps": float(row["Requests/s"]),
        "p50": float(row["50%"]), "p95": float(row["95%"]), "p99": float(row["99%"]),
        "cpu_api": statistics.mean(samples["api"]) if samples["api"] else 0.0,
        "cpu_db": statistics.mean(samples["db"]) if samples["db"] else 0.0,
        "cpu_redis": statistics.mean(samples["redis"]) if samples["redis"] else 0.0,
        "xact": x1 - x0,
        "hit_rate": hits / (hits + misses) if hits + misses else None,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Escenario: espera máx. {os.getenv('LOAD_WAIT', '0.05')} s; salida en {OUT}")
    results = [run_mode("cache-on", "true"), run_mode("cache-off", "false")]
    sh("docker", "compose", "up", "-d", "--force-recreate", "api")  # deja la caché activa

    on, off = results
    def pct(v):
        return "n/a" if v is None else f"{v * 100:.1f} %"

    lines = [
        f"# Resultado del experimento de caché ({USERS} usuarios, {DURATION}, mismo SKU, espera máx. {os.getenv('LOAD_WAIT', '0.05')} s)",
        "",
        "| Métrica | Con caché | Sin caché |",
        "| --- | --- | --- |",
        f"| Peticiones | {on['peticiones']} | {off['peticiones']} |",
        f"| Fallos | {on['fallos']} | {off['fallos']} |",
        f"| RPS | {on['rps']:.1f} | {off['rps']:.1f} |",
        f"| P50 (ms) | {on['p50']:.0f} | {off['p50']:.0f} |",
        f"| P95 (ms) | {on['p95']:.0f} | {off['p95']:.0f} |",
        f"| P99 (ms) | {on['p99']:.0f} | {off['p99']:.0f} |",
        f"| CPU API (media %) | {on['cpu_api']:.0f} | {off['cpu_api']:.0f} |",
        f"| CPU PostgreSQL (media %) | {on['cpu_db']:.0f} | {off['cpu_db']:.0f} |",
        f"| CPU Redis (media %) | {on['cpu_redis']:.0f} | {off['cpu_redis']:.0f} |",
        f"| Transacciones en PostgreSQL (`xact_commit`) | {on['xact']} | {off['xact']} |",
        f"| Tasa de hit | {pct(on['hit_rate'])} | {pct(off['hit_rate'])} |",
        "",
    ]
    (OUT / "resumen.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
