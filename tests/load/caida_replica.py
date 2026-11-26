"""Caída de una réplica de WH-002 bajo carga (F5, S-04).

Procedimiento: N clientes concurrentes piden GET /products a través de nginx
durante DURATION segundos, con PAUSE segundos de espera entre solicitudes.
Pasados KILL_AFTER segundos se apaga de inmediato un contenedor de la API
(`docker kill`) sin detener la carga. Cada solicitud se clasifica según el
instante en que se inició: antes o desde el apagado.

Uso:
    python tests/load/caida_replica.py <contenedor-a-apagar> \
        [--url http://127.0.0.1:8080/products] [--clients 8] \
        [--duration 25] [--kill-after 5] [--pause 0.05]

La clave se lee de API_KEY (por defecto dev-api-key). El script solo usa la
biblioteca estándar. Sale con código 1 si alguna solicitud posterior al
apagado no devuelve HTTP 200.
"""

import argparse
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request


def _request(url: str, key: str) -> str:
    req = urllib.request.Request(url, headers={"X-API-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:  # error de red o timeout
        return type(exc).__name__


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("container", help="contenedor de la réplica a apagar")
    parser.add_argument("--url", default="http://127.0.0.1:8080/products")
    parser.add_argument("--clients", type=int, default=8)
    parser.add_argument("--duration", type=float, default=25.0)
    parser.add_argument("--kill-after", type=float, default=5.0)
    parser.add_argument("--pause", type=float, default=0.05)
    args = parser.parse_args()

    key = os.getenv("API_KEY", "dev-api-key")
    start = time.monotonic()
    end = start + args.duration
    kill_started: list[float] = []  # instante real en que empieza el apagado
    lock = threading.Lock()
    results: list[tuple[bool, str]] = []  # (inició desde el apagado, resultado)

    def worker() -> None:
        while (began := time.monotonic()) < end:
            outcome = _request(args.url, key)
            with lock:
                after = bool(kill_started) and began >= kill_started[0]
                results.append((after, outcome))
            time.sleep(args.pause)

    threads = [threading.Thread(target=worker) for _ in range(args.clients)]
    for thread in threads:
        thread.start()

    time.sleep(args.kill_after)
    with lock:
        kill_started.append(time.monotonic())
    subprocess.run(["docker", "kill", args.container], check=True, capture_output=True)
    print(f"Apagado de {args.container} iniciado a los {kill_started[0] - start:.1f} s")
    for thread in threads:
        thread.join()

    failed_after = 0
    for label, after in (("Antes del apagado", False), ("Desde el inicio del apagado", True)):
        outcomes = [out for flag, out in results if flag == after]
        ok = sum(1 for out in outcomes if out == "200")
        other = len(outcomes) - ok
        if after:
            failed_after = other
        print(f"{label}: HTTP 200 = {ok}; otros HTTP o errores de red = {other}")
    return 1 if failed_after else 0


if __name__ == "__main__":
    raise SystemExit(main())
