# Preparacion de la defensa

Guía de ensayo pendiente de revisión grupal. Los títulos y la numeración son provisionales hasta cotejarlos con el enunciado del profesor.

## Índice

- Arquitectura - Preguntas 1 a 5
- Redis - Preguntas 6 a 10
- RabbitMQ - Preguntas 11 a 15
- Distribucion y CQRS - Preguntas 16 a 24
- Cloud - Preguntas 25 a 29
- Observabilidad - Preguntas 30 a 33
- Pregunta final: Escalamiento a 100 bodegas

## Arquitectura - Preguntas 1 a 5

Responsable: Santiago.

### 1. ¿Por qué separar la API de bodega y la central?

La bodega acepta escrituras locales y valida el stock. La central consolida lecturas y coordina transferencias. Separar ambos servicios permite operar una bodega sin invocar la central en cada movimiento. La vista global puede tener retraso. [Arquitectura](architecture.md)

### 2. ¿Qué datos deben persistir?

PostgreSQL conserva productos, inventario y movimientos. También persiste el outbox para recuperar eventos después de un fallo. Redis puede reconstruir la caché a partir de PostgreSQL. [Fase 1](fases/fase-1.md) · [ADR de Outbox](adr/0006-patron-outbox.md)

### 3. ¿Cómo se evita vender stock dos veces?

La operación bloquea la fila de inventario durante la transacción, comprueba la cantidad disponible y registra el movimiento junto al cambio de stock. Las salidas concurrentes sobre el mismo producto se serializan, lo que puede aumentar la espera en productos calientes. [ADR de concurrencia](adr/0004-control-de-concurrencia-en-movimientos.md)

### 4. ¿Por qué versionar el esquema SQL?

Las migraciones permiten reproducir la estructura y conservar restricciones explícitas. Generar tablas al iniciar la aplicación simplifica el prototipo, pero dificulta auditar cambios sobre bases existentes. [ADR de esquema](adr/0003-schema-sql-como-fuente-de-verdad.md)

### 5. ¿Qué gana el sistema con un balanceador?

Nginx distribuye las consultas de WH-002 y puede intentar otra réplica ante ciertos fallos. Las réplicas comparten almacenamiento, por lo que agregar API no elimina un cuello de botella en PostgreSQL. [ADR de Nginx](adr/0009-nginx-y-health-checks-pasivos.md)


## Redis - Preguntas 6 a 10

Responsable: Julian.

### 6. ¿Por qué Cache Aside?

La aplicación consulta Redis primero. Ante un miss, lee PostgreSQL y almacena la respuesta con TTL. Esto ahorra consultas repetidas y permite operar sin Redis, a cambio de una ventana de obsolescencia. [ADR de Redis](adr/0008-cache-aside-con-redis.md)

### 7. ¿En qué momento se invalida el inventario?

Después del commit. Invalidar antes permitiría que una lectura repueble la caché con el stock previo al commit. Una lectura ya iniciada aún puede repoblarla tarde, con el TTL como límite. [ADR de Redis](adr/0008-cache-aside-con-redis.md)

### 8. ¿Para qué sirve el TTL?

Limita cuánto dura una entrada sin renovarse y acota el impacto si falla el borrado. Un TTL más corto aumenta misses y carga en PostgreSQL. El valor documentado es 30 segundos. [ADR de Redis](adr/0008-cache-aside-con-redis.md)

### 9. ¿Qué pasa si Redis falla?

La API lee PostgreSQL y devuelve `X-Cache: BYPASS`. La prueba local de F10 observó HTTP 200 con más latencia durante la caída. [Evidencia F10 en E-07](https://github.com/julianandresdev/platform-warehouses/blob/7b84e133a8eb3c5b8d06c98298f7026723c07fa9/docs/fases/fase-10.md)

### 10. ¿Cómo se mide el aporte de la caché?

Comparar Redis habilitado y deshabilitado con la misma carga. En F2 se registraron 1795,7 frente a 827,4 solicitudes por segundo y P95 de 52 frente a 130 ms. Son resultados del entorno de la prueba. [Resultados F2](evidencias/fase-2/resumen.md)


## RabbitMQ - Preguntas 11 a 15

Responsable: David.

### 11. ¿Por qué RabbitMQ y exchanges separados?

Los exchanges de eventos permiten suscriptores independientes por clave. Los comandos se dirigen a una bodega. La comunicación asíncrona absorbe interrupciones cortas a cambio de colas, retraso y coordinación adicional. [ADR de RabbitMQ](adr/0005-topologia-rabbitmq.md)

### 12. ¿Qué problema resuelve Transactional Outbox?

El movimiento y la fila de outbox se confirman en la misma transacción. Un relay publica cuando el broker esté disponible. Se evita perder el evento entre el commit y el envío, con la posibilidad de republicación. [ADR de Outbox](adr/0006-patron-outbox.md)

### 13. ¿Cómo se evita aplicar dos veces un comando?

El consumidor registra el identificador en la misma transacción que el efecto. Si ya existe, confirma la entrega sin repetir el movimiento. La proyección también protege el estado mediante versiones. [ADR de idempotencia](adr/0020-idempotencia-comandos-bodega.md)

### 14. ¿Cuándo reintentar y cuándo enviar a DLQ?

El plan reserva reintentos acotados para fallos transitorios y DLQ para errores permanentes o agotados. La validación de esa política pertenece a D-05. [ADR de reintentos](adr/0015-reintentos-dlq-idempotencia.md)

### 15. ¿Qué pasa si el broker o el relay se detiene?

Los eventos ya confirmados quedan en el outbox. Al recuperar el componente, el relay reanuda el envío. La proyección global puede quedar temporalmente atrasada. [Evidencia F10 en E-07](https://github.com/julianandresdev/platform-warehouses/blob/7b84e133a8eb3c5b8d06c98298f7026723c07fa9/docs/fases/fase-10.md)


## Distribucion y CQRS - Preguntas 16 a 24

Responsable: Esteban.

Guía de ensayo basada en las fases F4 a F7. Los títulos y
la numeración 16–24 son provisionales hasta cotejarlos
con el enunciado del profesor.

### 16. ¿Por que utilizar una base de datos por bodega?

Una base compartida simplificaria las consultas globales,
pero aumentaria el acoplamiento entre bodegas.

Decidimos utilizar PostgreSQL independiente por bodega
para garantizar autonomia, aislamiento de datos y
escalamiento independiente.

La desventaja es que las consultas y transacciones
globales requieren mecanismos distribuidos.

Ver [Fase 4](fases/fase-4.md) y el [Compose distribuido](../infrastructure/compose/compose.distributed.yml).

### 17. ¿Como escalar bodegas con cargas diferentes?

No todas las bodegas reciben la misma cantidad de
solicitudes. Escalarlas de manera uniforme desperdicia
recursos.

Decidimos aumentar las replicas de API solamente en
las bodegas que necesitan mayor capacidad.

Nginx distribuye las solicitudes entre las replicas
de WH-002, que comparten su PostgreSQL y Redis.

Esto permite aumentar la capacidad, aunque la base
de datos puede convertirse en el nuevo cuello de botella.

En F5 se registraron 382.98 solicitudes por segundo
con una replica y 884.36 con tres replicas.

Ver [comparación de rendimiento con Locust](evidencias/fase-5/comparacion-rendimiento.md).

### 18. ¿Por que utilizar Saga para las transferencias?

Una transferencia involucra dos bases de datos
independientes y no dispone de una transaccion
ACID global.

Consideramos la coordinacion distribuida mediante
transacciones globales y el patron Saga.

Elegimos Saga porque permite realizar transacciones
locales y ejecutar operaciones compensatorias
cuando ocurre un fallo.

La desventaja es que existen estados intermedios
y consistencia eventual.

Ver [ADR-0013](adr/0013-saga-orquestada.md) y el [registro de integración de E-06](https://github.com/julianandresdev/platform-warehouses/blob/3888c2043a6909f6cf5323ddf26e2f1229aae838/docs/evidencias/fase-6/e06-integracion.md).

### 19. ¿Por que Saga orquestada y no coreografiada?

En una Saga coreografiada cada servicio reacciona
a eventos y determina la siguiente operacion.

En una Saga orquestada un coordinador central
administra los estados y emite los comandos.

Elegimos la segunda alternativa porque facilita
la trazabilidad, los timeouts, las compensaciones
y la recuperacion tras reinicios.

La desventaja es la dependencia del coordinador
para avanzar las transferencias.

Ver [ADR-0013](adr/0013-saga-orquestada.md).

### 20. ¿Que sucede cuando falla una transferencia?

La respuesta depende del estado de la transferencia.

- Reserva rechazada: FAILED.
- Reserva vencida despues de 30 segundos: FAILED.
- Reserva confirmada tardia: RELEASE_RESERVATION.
- Envío rechazado: `TRANSFER_SHIP_FAILED` lleva a `COMPENSATING` y se emite `RELEASE_RESERVATION`.
- Recepción rechazada: se emite `RETURN_STOCK`.
- Compensacion confirmada: CANCELLED.
- Destino temporalmente caido: DESTINATION_PENDING.

No se cancela automaticamente una transferencia
cuando la mercancia ya salio del origen, porque
podria duplicarse el inventario.

Despues de cinco minutos de espera se registra
una alerta.

El objetivo es conservar el inventario, incluyendo
las unidades que se encuentran en transito.

E-06 registró 46 pruebas unitarias y cinco escenarios de
integración exitosos, incluidas las compensaciones por
rechazo del destino y por fallo de envío inducido. El PR
de E-06 contiene esa evidencia.

Ver [resultados de F6 en E-06](https://github.com/julianandresdev/platform-warehouses/blob/3888c2043a6909f6cf5323ddf26e2f1229aae838/docs/fases/fase-6.md).

### 21. ¿Que es CQRS y por que lo utilizamos?

CQRS separa las operaciones de escritura de las
consultas de lectura.

Las bodegas conservan sus bases operacionales,
mientras que la central mantiene un modelo de
lectura con el inventario consolidado.

RabbitMQ transporta los eventos y el worker
de proyeccion actualiza PostgreSQL central.

Esto reduce la dependencia de las APIs remotas
y mejora la disponibilidad de las consultas.

La desventaja es la consistencia eventual y
la complejidad de mantener la proyeccion.

Ver [ADR-0012](adr/0012-proyeccion-cqrs.md).

### 22. ¿Como se mantiene actualizado el Read Model?

Cada cambio de inventario produce un evento
INVENTORY_UPDATED con su version correspondiente.

El worker central realiza un UPSERT utilizando
la llave compuesta SKU y warehouse_id.

Solo se actualiza un registro si la version
recibida es mayor que la version almacenada.

Adicionalmente se utiliza processed_messages
para controlar eventos duplicados.

Esto evita que un mensaje antiguo sobrescriba
informacion mas reciente.

La proyeccion puede presentar retrasos, medidos
mediante projection_lag_seconds.

Ver [pruebas de versiones de la proyección](../tests/unit/test_projection_version.py) y [Fase 7](fases/fase-7.md).

### 23. ¿Que ocurre si una bodega deja de responder?

La central conserva el ultimo inventario conocido
en su base de datos.

Si una bodega permanece mas de 90 segundos sin
enviar un heartbeat, se marca como stale.

Esto permite continuar respondiendo consultas,
pero advierte que los datos pueden estar
desactualizados.

Fan-out, en cambio, depende de las respuestas
HTTP de las bodegas y puede devolver datos
parciales o errores.

Ver [experimento de caída en Fase 7](fases/fase-7.md) y [resultado CQRS](evidencias/fase-7/cqrs_fallo_stats.csv).

### 24. ¿Que alternativa es mejor: Fan-out o CQRS?

Fan-out consulta las APIs de las bodegas en paralelo.
CQRS consulta el modelo consolidado de la central.

En los experimentos locales de E-05 se obtuvieron:

| Metrica | CQRS | Fan-out |
| --- | ---: | ---: |
| Latencia media normal | 93.75 ms | 349.88 ms |
| P95 normal | 200 ms | 580 ms |
| Solicitudes por segundo | 98.52 | 42.64 |
| Solicitudes exitosas ante el fallo probado | 100% (6283 de 6283) | 0.58% (8 de 1386) |

Elegimos CQRS como mecanismo predeterminado
porque presento menor latencia y mayor disponibilidad
bajo las condiciones evaluadas.

Fan-out consulta directamente las bodegas, pero
no garantiza un snapshot global atomico.

CQRS sacrifica la actualidad inmediata de los
datos a cambio de disponibilidad y desacoplamiento.

Los resultados corresponden a pruebas locales
y no son garantias de rendimiento en produccion.

Ver [resultados de Fase 7](fases/fase-7.md) y [archivos del experimento](evidencias/fase-7/).

## Cloud - Preguntas 25 a 29

Responsable: Santiago.

### 25. ¿Qué se gana con Terraform?

Permite revisar el plan, reproducir la configuración y auditar qué recursos quedan al desmontar el entorno. Requiere gestionar el estado y contar con permisos y cuotas del laboratorio. [ADR de despliegue](adr/0018-despliegue-aws-learner-lab.md)

### 26. ¿Cómo se distribuyen las funciones en AWS?

El diseño asigna imágenes a ECR, ejecución de servicios a EC2, persistencia relacional a RDS y reportes a S3. Lambda se activa por eventos de objetos. La topología final necesita evidencia de S-09. [Arquitectura](architecture.md)

### 27. ¿Por qué MinIO en local y S3 en AWS?

MinIO permite probar el flujo de objetos desde Compose. S3 aporta la integración administrada con el entorno AWS. Los permisos y notificaciones se verifican aparte. [ADR de almacenamiento](adr/0011-minio-local-y-s3-en-aws.md)

### 28. ¿Cuándo utilizar un worker, un batch o Lambda?

El worker se mantiene disponible para consumo continuo. Batch agrupa trabajo con horario o volumen definido. Lambda procesa eventos breves y puede tener arranque en frío. Las mediciones de AWS deben respaldar una comparación de duración y costo. [ADR de Lambda](adr/0017-lambda-validacion-eventos.md)

### 29. ¿Cómo se controla el costo de la práctica?

Registrar la duración y los recursos por sesión, verificar el resultado del desmontaje y contrastarlo con la hoja de gasto. El costo total requiere datos de la sesión de AWS. [Despliegue AWS](aws.md)


## Observabilidad - Preguntas 30 a 33

Responsable: Julian.

### 30. ¿Qué métricas se deben mirar durante una prueba de carga?

RPS, P95/P99, errores, CPU, memoria y colas. En la vista global se añade el retraso de la proyección. Correlacionarlas permite ubicar el recurso saturado y distinguirlo de un generador de carga saturado. [Fase 11](fases/fase-11.md)

### 31. ¿Cómo se sigue una transferencia?

Propagar el identificador de correlación desde el POST inicial a los comandos, respuestas y logs. El historial de la API verifica el orden y el estado final. [Traza del PR de E-07](https://github.com/julianandresdev/platform-warehouses/blob/7b84e133a8eb3c5b8d06c98298f7026723c07fa9/docs/evidencias/fase-11/traza-transferencia-saga.json)

### 32. ¿Qué indica el retraso de proyección?

Mide cuánto tarda un evento en quedar reflejado en el modelo de lectura. El heartbeat mide si la bodega sigue reportando actividad. Una vista puede responder y arrastrar retraso aunque su HTTP sea exitoso. [ADR de CQRS](adr/0012-proyeccion-cqrs.md)

### 33. ¿Qué aporta Grafana a un diagnóstico?

Relacionar series de latencia, errores, CPU y colas en el mismo intervalo. Los logs sirven luego para explicar una operación concreta. Los dashboards definitivos deben verificarse durante una corrida real. [ADR de observabilidad](adr/0016-prometheus-y-grafana.md)


## Pregunta final: Escalamiento a 100 bodegas

Responsables: Julian y Esteban.

Estado: Borrador pendiente de revision conjunta.

### Problema

La empresa necesita administrar 100 bodegas con
diferentes niveles de demanda, manteniendo autonomia,
consistencia local y disponibilidad de consultas globales.

### Alternativas

1. Una aplicacion y una base de datos centralizadas.
2. Replicar uniformemente toda la infraestructura.
3. Arquitectura distribuida con escalamiento
   independiente por bodega.

### Decision

Utilizar una arquitectura distribuida donde cada bodega
disponga de su propia API, PostgreSQL y Redis.

Las bodegas de mayor demanda tendran mas replicas de API
detras de un balanceador de carga.

Las bodegas de menor demanda utilizaran menos recursos.

RabbitMQ y Transactional Outbox permitiran desacoplar
las operaciones y conservar eventos pendientes ante fallos.

La plataforma central utilizara CQRS para consultar
el inventario consolidado sin realizar 100 solicitudes
HTTP por cada consulta global.

Las transferencias se coordinaran mediante Saga,
con estados persistentes, idempotencia y compensaciones.

### Estrategia de escalamiento

- Escalar las APIs horizontalmente segun la demanda.
- Utilizar Redis para reducir consultas repetitivas.
- Monitorear conexiones y saturacion de PostgreSQL.
- Escalar consumidores segun la acumulacion de mensajes.
- Mantener las consultas globales sobre el Read Model.
- Evaluar particionamiento y alta disponibilidad de RabbitMQ.
- Automatizar el aprovisionamiento mediante Terraform.
- Utilizar S3 y procesamiento Batch para reportes.
- Monitorear latencias, errores y retraso de proyeccion.

### Evidencia experimental

| Experimento | Configuracion inicial | Configuracion optimizada |
| --- | ---: | ---: |
| F2 - Rendimiento Redis | 827.4 RPS sin cache | 1795.7 RPS con cache |
| F2 - P95 | 130 ms sin cache | 52 ms con cache |
| F5 - Escalamiento API | 382.98 RPS con 1 replica | 884.36 RPS con 3 replicas |
| F5 - Fallos registrados | 500 | 0 |
| F7 - Latencia media | 349.88 ms Fan-out | 93.75 ms CQRS |
| F7 - Disponibilidad HTTP ante fallo | 0.58% Fan-out | 100% CQRS |

Los resultados corresponden a experimentos locales
realizados bajo condiciones especificas.

### Trade-offs

- Mayor complejidad operativa.
- Consistencia eventual del inventario global.
- Necesidad de monitorear eventos y consumidores.
- Coordinacion de transacciones distribuidas.
- Mayor cantidad de servicios y bases de datos.
- Costos de infraestructura y mantenimiento.

### Consecuencias

La arquitectura permite distribuir recursos segun
las necesidades de cada bodega.

Una falla local no necesariamente interrumpe
la operacion de las demas bodegas.

La central puede conservar el ultimo estado conocido
aunque una bodega se encuentre temporalmente inaccesible.

### Limitaciones

Las pruebas realizadas respaldan las decisiones de
cache, escalamiento horizontal y CQRS.

Sin embargo, no demuestran capacidad real para operar
100 bodegas simultaneamente.

Se requieren pruebas de carga desigual, carga progresiva,
saturacion del broker, recuperacion y despliegue completo.

### Conclusion

La solucion propuesta escala por dominio y por demanda,
evitando que todas las operaciones dependan de una
unica API o base de datos operacional.

La arquitectura debe evolucionar segun las metricas
obtenidas y no mediante una cantidad fija de replicas.

### Referencias

- docs/architecture.md
- docs/load-testing.md (E-07)
- docs/fases/fase-7.md (E-05)
- docs/evidencias/fase-2/
- docs/evidencias/fase-5/
- docs/adr/0012-proyeccion-cqrs.md
- docs/adr/0013-saga-orquestada.md

Las evidencias de otras ramas deben quedar disponibles
en main despues de su integracion.
