# Fase 12 - IoT en bodegas

Líder: David · Apoyo: Santiago

Estado: Implementado localmente; la corrida de diez minutos se ejecutó, pero el balance final no cumplió el criterio de aceptación.

## Qué se construyó

- Perfil `iot` de Docker Compose con Mosquitto, PostgreSQL IoT, gateway MQTT, workers de almacenamiento y alertas, y simulador.
- Simulador configurable para 100 sensores lógicos distribuidos en WH-001 a WH-005. Publica cinco tipos de mediciones cada dos segundos mediante MQTT QoS 1, con identificador de evento, secuencia por sensor y timestamp.
- Controles para duplicados (`DUP_RATE`), reordenamiento (`REORDER_RATE`) e interrupción simulada. Durante el corte, SQLite conserva la secuencia y las mediciones pendientes; al recuperar la conectividad las reenvía.
- Gateway suscrito a `warehouses/+/sensors/+`: valida tópico y payload, convierte cada lectura a `SENSOR_READING`, publica en RabbitMQ con confirmación y confirma el mensaje MQTT después. Los inválidos se envían con confirmación a `iot.ingestion.dlq`.
- Worker de almacenamiento idempotente por `event_id`. Conserva lecturas fuera de orden, pero solo avanza `sensor_state` con una secuencia mayor. El contador de huecos se calcula por las secuencias ausentes bajo el último valor observado.
- Worker de alertas de temperatura: emite una alerta después de tres mediciones altas consecutivas y no repite la alerta activa del sensor. Persiste la alerta antes de publicarla mediante una tabla outbox.
- Métricas Prometheus para lecturas, latencias, duplicados, reordenamiento, huecos, buffer local y alertas.

## Cierre de la fase

Los siete tests unitarios IoT cubren contrato y ruteo MQTT, persistencia del spool, secuencias y regla de alertas. `tests/iot/smoke.sh` pasó con un recorrido corto de extremo a extremo con duplicados, reordenamiento y corte de red. La aceptación completa definida por el plan es `scripts/iot/run-acceptance.sh`: dura diez minutos con 100 sensores y deja el resumen en `docs/evidencias/fase-12/simulacion-10min.json`.

La corrida produjo 30.000 lecturas únicas y 30.606 publicaciones MQTT confirmadas. En el corte de verificación, PostgreSQL mostraba 29.784 lecturas únicas, 599 duplicados descartados y 1.412 entregas fuera de orden; el total procesado era 30.383, 223 por debajo de las publicaciones confirmadas. Se observaron 216 huecos de secuencia y la métrica los igualó. Por eso queda una discrepancia pequeña pero real de mensajes/duplicados al cierre; esta rama no afirma que el criterio de balance haya pasado. La prueba corta y los tests unitarios sí pasaron. El panel de Grafana forma parte de la infraestructura de observabilidad compartida y se debe conectar a los endpoints de métricas de los servicios.

## Decisiones

| Decisión | Elegido | Por qué |
| --- | --- | --- |
| Transporte sensor-gateway | MQTT QoS 1 | Entrega confirmada con deduplicación de extremo a extremo por `event_id`. |
| Store-and-forward | SQLite con sincronización completa | Conserva lecturas y secuencias cuando el gateway no está disponible. |
| Persistencia de lecturas | PostgreSQL, lectura única por `event_id` | Idempotencia durable y consultas de estado por sensor. |
| Alertas | Umbral configurable y tres lecturas altas consecutivas | Reduce alertas por picos aislados; el estado activo y el outbox sobreviven reinicios. |

## Preguntas del profesor

- ¿Por qué QoS 1 y deduplicación en lugar de QoS 2? QoS 1 da entrega al menos una vez; la clave `event_id` elimina el efecto duplicado de forma durable en el consumidor.
- ¿Qué pasa si la red cae? El simulador guarda eventos y secuencias en SQLite y los vacía al reconectar; RabbitMQ confirma la publicación antes del ack MQTT.
- ¿Cómo se conserva el orden? Cada sensor tiene secuencia independiente. Una lectura tardía se registra, pero no reemplaza el estado de una secuencia mayor.
- ¿Cómo se calculan huecos? Para cada sensor se compara su secuencia máxima con la cantidad de secuencias únicas almacenadas; el resultado es una señal operativa y los eventos tardíos pueden reducir la brecha observada.

## Evidencia

- `docs/evidencias/fase-12/simulacion-smoke.json`: resumen de la prueba corta, generado por `tests/iot/smoke.sh`.
- `docs/evidencias/fase-12/simulacion-10min.json`: resumen requerido de la aceptación de diez minutos, generado por `scripts/iot/run-acceptance.sh`.
- `docs/evidencias/fase-12/simulacion-10min-validacion.json`: resultado de los conteos y la diferencia observada en la corrida.
- `docs/evidencias/fase-12/diagnostico-180s.json`: corrida diagnóstica de tres minutos con balance exacto y cero huecos.
- Métricas disponibles en los puertos locales 19102–19105 del Compose normal; las pruebas aisladas usan 29102–29105.
- `tests/iot/README.md`: instrucciones de ejecución y validación.
