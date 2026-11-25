# Informe de resiliencia y pruebas de carga — E-07

## 1. Entorno

Docker Compose local, tres bodegas independientes,
PostgreSQL, Redis, RabbitMQ, Nginx y plataforma central.
Pruebas manuales realizadas el 24 de noviembre de 2026
sobre la rama E-06.

## 2. Resiliencia (F10)

| Escenario | Resultado observado |
|---|---|
| Redis detenido | HTTP 200, cache BYPASS, inventario intacto |
| RabbitMQ detenido | HTTP 201, evento persistido y publicado tras 2 intentos |
| Worker detenido | Evento pendiente y publicado tras reiniciar |
| Evento duplicado | Inventario central permanece en 35 unidades, versión 3 |
| Bodega inaccesible | Fan-out devuelve respuesta parcial e identifica WH-003 |

### Hallazgos

- Redis: latencia individual de 1045.23 ms antes del fallo
  y 4019.40 ms durante el fallo.
- Transactional Outbox permite conservar los eventos pendientes.
- La proyección central conserva el estado ante eventos duplicados.
- Fan-out presentó respuestas parciales incluso antes del fallo
  provocado. Posible causa: timeout de 500 ms.
- WH-003 fue reiniciada, pero no se verificó el Fan-out posterior.
- Se recomienda ajustar los timeouts y verificar la recuperación.

Los scripts oficiales D-06 quedan pendientes de revisión.

## 3. Escenario 1: Redis ON/OFF

- Escenario: lecturas repetidas del mismo SKU.
- Carga: 100 usuarios, 2 minutos.
- Arquitectura: API, PostgreSQL y Redis opcional.
- Métricas: RPS, percentiles, CPU y errores.
- Resultados:

| Métrica | Redis ON | Redis OFF |
|---|---:|---:|
| RPS | 1795.7 | 827.4 |
| P50 (ms) | 27 | 92 |
| P95 (ms) | 52 | 130 |
| P99 (ms) | 66 | 160 |
| Fallos | 0 | 0 |
| CPU PostgreSQL (%) | 1 | 18 |

- Cuello de botella: posible saturación de API y consultas a BD.
- Hipótesis: Redis reduce las consultas repetitivas a PostgreSQL.
- Evidencia: [Experimento F2](evidencias/fase-2/resumen.md).
- Mejora: ajustar pool, TTL y monitorear hit ratio.

## 4. Escenario 2: Escalamiento horizontal

- Escenario: una réplica frente a tres réplicas.
- Carga: 100 usuarios, 3 minutos, incorporación de 10 usuarios/s.
- Arquitectura: Nginx, FastAPI y PostgreSQL.
- Métricas: RPS, latencia y errores.
- Resultados:

| Métrica | 1 réplica | 3 réplicas |
|---|---:|---:|
| RPS | 382.98 | 884.36 |
| Latencia promedio (ms) | 152.37 | 8.80 |
| P95 (ms) | 69 | 16 |
| P99 (ms) | 150 | 26 |
| Fallos | 500 | 0 |

- Cuello de botella: posible saturación de la instancia única.
- Hipótesis: distribuir solicitudes reduce la presión por réplica.
- Evidencia: [Experimento F5](evidencias/fase-5/comparacion-rendimiento.md).
- Mejora: escalamiento automático según demanda.

## 5. Escenario 3: Carga desigual entre bodegas

- Escenario: distribución asimétrica de solicitudes.
- Carga: 50, 800 y 20 usuarios respectivamente.
- Arquitectura: tres bodegas independientes.
- Métricas: RPS, P95, P99, CPU, memoria y errores.
- Resultados: pendientes de J-09.
- Cuello de botella: pendiente de medición.
- Hipótesis: WH-002 requerirá mayor capacidad.
- Evidencia: pendiente.
- Mejora: escalamiento independiente por bodega.

## 6. Escenario 4: Carga progresiva

- Escenario: identificar el límite de capacidad.
- Carga: 100, 500, 1000 y 5000 usuarios.
- Arquitectura: plataforma distribuida y Locust.
- Métricas: RPS, latencia, errores, CPU y memoria.
- Resultados: pendientes de J-09.
- Cuello de botella: pendiente de medición.
- Hipótesis: la saturación puede ocurrir en API, BD o Locust.
- Evidencia: pendiente.
- Mejora: distribuir el generador de carga si se satura.

## 7. Pregunta final: 100 bodegas con cargas diferentes

La arquitectura debe escalar independientemente por bodega,
asignando más réplicas a las de mayor demanda y evitando
sobredimensionar las de menor tráfico.

Redis reduce consultas repetitivas a PostgreSQL.
RabbitMQ y Transactional Outbox desacoplan las operaciones.
CQRS permite consultar una proyección central sin realizar
100 solicitudes simultáneas mediante Fan-out.

Las transferencias distribuidas se coordinan mediante Saga.
Prometheus y Grafana deben identificar saturación, latencias,
errores y acumulación de mensajes para orientar el escalamiento.

Los experimentos F2 y F5 respaldan el uso de caché y réplicas,
pero no demuestran todavía capacidad para 100 bodegas.

## 8. Estado del informe

Borrador para revisión de Julian.
Pendientes: scripts D-06, experimentos J-09, capturas de
Grafana, trazabilidad de transferencias y revisión final.

Los resultados de carga corresponden a experimentos anteriores
del repositorio; no fueron ejecutados nuevamente en E-07.
