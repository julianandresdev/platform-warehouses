# Preparacion de la defensa

Estado: Borrador consolidado pendiente de revision grupal.

## Indice

- Arquitectura - Preguntas 1 a 5
- Redis - Preguntas 6 a 10
- RabbitMQ - Preguntas 11 a 15
- Distribucion y CQRS - Preguntas 16 a 24
- Cloud - Preguntas 25 a 29
- Observabilidad - Preguntas 30 a 33
- Pregunta final: Escalamiento a 100 bodegas

## Arquitectura - Preguntas 1 a 5

Responsable: Santiago.

Pendiente de incorporar las respuestas del responsable.


## Redis - Preguntas 6 a 10

Responsable: Julian.

Pendiente de incorporar las respuestas del responsable.


## RabbitMQ - Preguntas 11 a 15

Responsable: David.

Pendiente de incorporar las respuestas del responsable.


## Distribucion y CQRS - Preguntas 16 a 24

Responsable: Esteban.

Borrador tematico basado en las fases F4 a F7.
La numeracion y redaccion deben contrastarse con
las preguntas originales del profesor.

### 16. ¿Por que utilizar una base de datos por bodega?

Una base compartida simplificaria las consultas globales,
pero aumentaria el acoplamiento entre bodegas.

Decidimos utilizar PostgreSQL independiente por bodega
para garantizar autonomia, aislamiento de datos y
escalamiento independiente.

La desventaja es que las consultas y transacciones
globales requieren mecanismos distribuidos.

Evidencia: arquitectura distribuida y pruebas F4.

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

Evidencia: docs/evidencias/fase-5/.

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

Evidencia: ADR-0013 y pruebas de E-06.

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

Evidencia: ADR-0013.

### 20. ¿Que sucede cuando falla una transferencia?

La respuesta depende del estado de la transferencia.

- Reserva rechazada: FAILED.
- Reserva vencida despues de 30 segundos: FAILED.
- Reserva confirmada tardia: RELEASE_RESERVATION.
- Recepcion rechazada: RETURN_STOCK.
- Compensacion confirmada: CANCELLED.
- Destino temporalmente caido: DESTINATION_PENDING.

No se cancela automaticamente una transferencia
cuando la mercancia ya salio del origen, porque
podria duplicarse el inventario.

Despues de cinco minutos de espera se registra
una alerta.

El objetivo es conservar el inventario, incluyendo
las unidades que se encuentran en transito.

Las pruebas centrales simuladas fueron exitosas.
La validacion integral de los seis experimentos
debe confirmarse junto con J-07.

Evidencia: ADR-0013 y documentacion F6.

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

Evidencia: ADR-0012.

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

Evidencia: pruebas de versiones y duplicados E-04.

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

Evidencia: experimento de caida de WH-002 en E-05.

### 24. ¿Que alternativa es mejor: Fan-out o CQRS?

Fan-out consulta las APIs de las bodegas en paralelo.
CQRS consulta el modelo consolidado de la central.

En los experimentos locales de E-05 se obtuvieron:

| Metrica | CQRS | Fan-out |
| --- | ---: | ---: |
| Latencia media normal | 93.75 ms | 349.88 ms |
| P95 normal | 200 ms | 580 ms |
| Solicitudes por segundo | 98.52 | 42.64 |
| Disponibilidad HTTP ante fallo | 100% | 0.58% |

Elegimos CQRS como mecanismo predeterminado
porque presento menor latencia y mayor disponibilidad
bajo las condiciones evaluadas.

Fan-out consulta directamente las bodegas, pero
no garantiza un snapshot global atomico.

CQRS sacrifica la actualidad inmediata de los
datos a cambio de disponibilidad y desacoplamiento.

Los resultados corresponden a pruebas locales
y no son garantias de rendimiento en produccion.

Evidencia: docs/fases/fase-7.md y experimentos E-05.

## Cloud - Preguntas 25 a 29

Responsable: Santiago.

Pendiente de incorporar las respuestas del responsable.


## Observabilidad - Preguntas 30 a 33

Responsable: Julian.

Pendiente de incorporar las respuestas del responsable.


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
