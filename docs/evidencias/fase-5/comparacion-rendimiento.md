# Fase 5 — Pruebas de rendimiento y escalamiento horizontal

## Herramientas
- Docker Compose
- Nginx
- Locust
- FastAPI
- PostgreSQL

## Configuración de pruebas
- Usuarios virtuales: 100
- Incorporación: 10 usuarios por segundo
- Duración configurada: 3 minutos
- Pausa entre solicitudes: 0,05 a 0,15 segundos
- Endpoints: GET /products y GET /inventory/1

## Resultados

| Métrica | 1 réplica | 3 réplicas |
|---|---:|---:|
| Solicitudes | 64290 | 157873 |
| Requests/s | 382.98 | 884.36 |
| Latencia promedio (ms) | 152.37 | 8.80 |
| P50 (ms) | 30 | 4 |
| P95 (ms) | 69 | 16 |
| P99 (ms) | 150 | 26 |
| Fallos | 500 | 0 |

## Análisis
El rendimiento medido aumentó aproximadamente un 130,9 % al
escalar de una a tres réplicas.

La latencia promedio disminuyó aproximadamente un 94,2 %.

Con una réplica se registraron 500 respuestas HTTP 504.
Con tres réplicas no se registraron errores.

Los resultados muestran una mejora del rendimiento y la
estabilidad bajo la carga aplicada.

## Limitaciones
Las pruebas se realizaron en un entorno Docker local.
Los resultados pueden variar según los recursos disponibles.
El experimento no demuestra una mejora lineal ni garantiza
el mismo comportamiento en producción.
