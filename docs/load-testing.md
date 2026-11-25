# Informe de resiliencia y pruebas de carga — E-07

## 1. Entorno

Pruebas manuales realizadas el 25 de noviembre de 2026
mediante Docker Compose local, con tres bodegas independientes,
PostgreSQL, Redis, RabbitMQ, Nginx y plataforma central.

Rama local: `feat/E-06-saga`.

Commit del repositorio local:
`444355dbff5f327f14327e835b96d791b1e7aa70`.

Se reutilizaron imágenes existentes, sin reconstruirlas.
El commit identifica el código local, no certifica la
procedencia exacta de todas las imágenes.

Evidencia: [Entorno de pruebas](evidencias/fase-10/entorno-pruebas.txt).

## 2. Resiliencia (F10)

### 2.1. Redis detenido

Se realizaron tres consultas por etapa sobre P-001 en WH-001.

| Indicador | Antes | Durante | Después |
|---|---:|---:|---:|
| HTTP | 200 | 200 | 200 |
| Cantidad | 100 | 100 | 100 |
| Cache | MISS/HIT | BYPASS | HIT |
| Latencia promedio (ms) | 7.53 | 3380.58 | 6.37 |
| Solicitudes exitosas | 3/3 | 3/3 | 3/3 |

Cache Aside permitió mantener disponibles las lecturas
desde PostgreSQL. La caída incrementó considerablemente
la latencia. Se recomienda revisar los timeouts y reintentos.

Evidencias:
[Antes](evidencias/fase-10/redis-antes-1.txt),
[Durante](evidencias/fase-10/redis-durante-1.txt),
[Después](evidencias/fase-10/redis-despues-1.txt).

### 2.2. RabbitMQ detenido

Se registró una entrada de una unidad en WH-001 con
RabbitMQ apagado. La API respondió HTTP 201.

- Cantidad: 100 a 101 unidades.
- Versión: 1 a 2.
- El evento permaneció pendiente en outbox.
- Fue publicado después de recuperar RabbitMQ.
- Intentos de publicación: 2.
- Tiempo entre creación y publicación: 27.02 segundos.
- La proyección central incorporó las 101 unidades de WH-001.

Transactional Outbox permitió conservar el movimiento
y su evento durante la indisponibilidad del broker.

Evidencias:
[Movimiento](evidencias/fase-10/rabbitmq-movimiento.txt),
[Pendiente](evidencias/fase-10/rabbitmq-outbox-pendiente.txt),
[Publicado](evidencias/fase-10/rabbitmq-outbox-publicado.txt),
[Proyección](evidencias/fase-10/rabbitmq-proyeccion-central.txt).

### 2.3. Worker detenido

Se detuvo el worker de WH-001 manteniendo RabbitMQ activo.

- El movimiento respondió HTTP 201.
- Cantidad: 101 a 102 unidades.
- Versión: 2 a 3.
- Evento pendiente con cero intentos de publicación.
- Después de reiniciar el worker, fue publicado en un intento.
- Tiempo entre creación y publicación: 7.22 segundos.
- CQRS incorporó correctamente la nueva cantidad.

Esta prueba valida la recuperación del relay de outbox.
No sustituye una prueba específica de acumulación de
mensajes con un consumidor RabbitMQ detenido.

Evidencias:
[Worker detenido](evidencias/fase-10/worker-detenido.txt),
[Movimiento](evidencias/fase-10/worker-movimiento.txt),
[Pendiente](evidencias/fase-10/worker-outbox-pendiente.txt),
[Publicado](evidencias/fase-10/worker-outbox-publicado.txt).

### 2.4. Evento duplicado

Se publicaron dos copias del evento
`d79b3f49-bca4-4be0-b522-78146fe932d7`,
conservando su identificador, contenido y versión.

| Indicador | Antes | Después |
|---|---:|---:|
| Cantidad WH-001 | 102 | 102 |
| Versión | 3 | 3 |
| Cantidad reservada | 0 | 0 |

La fecha de actualización tampoco cambió.
La cola central.projection terminó sin mensajes pendientes
ni mensajes sin confirmar, con un consumidor activo.

El resultado respalda la idempotencia de la proyección.
No se obtuvo un log individual del descarte de cada evento.
Tampoco se verificó la deduplicación de auditoría.

Evidencias:
[Evento original](evidencias/fase-10/duplicado-evento-original.json),
[Publicación](evidencias/fase-10/duplicado-publicacion.txt),
[Antes](evidencias/fase-10/duplicado-antes.txt),
[Después](evidencias/fase-10/duplicado-despues.txt),
[Colas](evidencias/fase-10/duplicado-colas.txt).

### 2.5. Bodega inaccesible

Se detuvo exclusivamente la API de WH-003 y se realizaron
tres consultas Fan-out por etapa.

| Indicador | Antes | Durante | Después |
|---|---:|---:|---:|
| HTTP | 200 | 200 | 200 |
| Cantidad consultada | 190 | 135 | 190 |
| Bodegas disponibles | 3 | 2 | 3 |
| Partial | false | true | false |
| Latencia promedio (ms) | 77.37 | 509.16 | 48.02 |
| Solicitudes exitosas | 3/3 | 3/3 | 3/3 |

Durante el fallo, unavailable identificó exclusivamente
a WH-003. Después de reiniciar la API, las 55 unidades
volvieron a estar disponibles mediante Fan-out.

Las latencias durante el fallo son coherentes con el
timeout de 500 ms.

No se reprodujeron las respuestas parciales previas
al fallo observadas el 24 de noviembre. Su causa original
continúa sin confirmarse.

La prueba demuestra recuperación mediante Fan-out,
no una transición a stale por ausencia de heartbeats.

Evidencias:
[Antes](evidencias/fase-10/fanout-antes-1.txt),
[Durante](evidencias/fase-10/fanout-durante-1.txt),
[Después](evidencias/fase-10/fanout-despues-1.txt),
[Recuperación](evidencias/fase-10/wh003-recuperada.txt).

### 2.6. Hallazgo adicional: inicialización de CQRS

Después de las pruebas de RabbitMQ y del worker,
Fan-out devolvió 192 unidades y CQRS solamente 137.

WH-003 tenía 55 unidades de P-001 en PostgreSQL,
pero carecía de una fila correspondiente en global_inventory.
Los heartbeats funcionaban y su outbox estaba vacío.

Se registró una entrada y una salida de una unidad
mediante la API de WH-003. Ambos eventos se publicaron
en un intento y fueron incorporados a la proyección.

| Bodega | CQRS final | Fan-out final |
|---|---:|---:|
| WH-001 | 102 | 102 |
| WH-002 | 35 | 35 |
| WH-003 | 55 | 55 |
| Total | 192 | 192 |

Se restauró la cantidad original de WH-003.
La versión avanzó de 1 a 3.

El resultado es compatible con una falta de inicialización
del read model a partir de los datos del seed.
Se recomienda implementar una sincronización inicial
y un mecanismo de reconciliación por SKU y bodega.

La prueba resuelve la discrepancia para P-001,
pero no constituye una corrección general del sistema.

Evidencias:
[Diagnóstico](evidencias/fase-10/diagnostico-cqrs-wh003.txt),
[Outbox](evidencias/fase-10/wh003-sync-outbox.txt),
[CQRS](evidencias/fase-10/wh003-sync-cqrs.txt),
[Fan-out](evidencias/fase-10/wh003-sync-fanout.txt).

### 2.7. Alcance y limitaciones

Los cinco escenarios fueron ejecutados manualmente.
Las mediciones corresponden a solicitudes individuales,
no a experimentos de carga concurrente.

Los scripts oficiales D-06, las pruebas de retry/DLQ,
la matriz de errores y las verificaciones adicionales
de consumidores y auditoría siguen pendientes de validación.

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

- Cinco escenarios manuales de resiliencia ejecutados.
- Evidencias de las pruebas del 25 de noviembre adjuntas.
- Recuperación de WH-003 verificada mediante Fan-out.
- Discrepancia de CQRS diagnosticada y resuelta para P-001.
- Resultados históricos de F2 y F5 consolidados.
- Escenarios 3 y 4 pendientes de resultados oficiales J-09.
- Pendientes: scripts D-06, matriz de errores, CSV de Locust,
  capturas de Grafana y trazabilidad de una transferencia.
- Pendiente de revisión final de Julian.

Los resultados históricos de carga corresponden a
experimentos anteriores del repositorio y no fueron
ejecutados nuevamente durante estas pruebas manuales.

Las pruebas realizadas no certifican todavía capacidad
para operar 100 bodegas simultáneamente.
