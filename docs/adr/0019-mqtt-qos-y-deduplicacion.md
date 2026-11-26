# ADR-0019 — MQTT, QoS y deduplicación de lecturas IoT

## Estado

Aceptado para la implementación local de D-07. Los tests unitarios y la prueba corta validan el contrato; la corrida de diez minutos está registrada en `docs/evidencias/fase-12/`, aunque el conteo final mostró una diferencia que requiere seguimiento antes de afirmar que se cumple el balance de extremo a extremo.

## Contexto y alternativas

Los sensores pueden perder conectividad y reenviar lecturas. QoS 0 reduce el intercambio de mensajes, pero puede perder entregas. QoS 2 añade intercambios en el tramo MQTT. QoS 1 con deduplicación persistente permite detectar reenvíos en el flujo completo.

## Decisión

Publicar lecturas con MQTT QoS 1, `event_id`, número de secuencia y timestamp. Mantener un búfer local y republicar al recuperar conectividad. La ingestión valida y publica en RabbitMQ. El almacenamiento deduplica por `event_id` y solo actualiza el estado del sensor cuando la secuencia aumenta. Medir por separado duplicados, lecturas fuera de orden y huecos.

## Consecuencias y validación

El búfer requiere límites y el orden es por sensor. Un hueco observado puede corresponder a una lectura tardía, por lo que se debe declarar la ventana de medición. El [issue D-07](https://github.com/julianandresdev/platform-warehouses/issues/21) requiere una corrida de diez minutos y un corte de red documentado. Ver [fase de IoT](../fases/fase-12.md).
