# Preparación de la defensa

Guía de ensayo alineada con el orden y los temas de la [sección 33 del enunciado del profesor](https://github.com/SebastianReyesLeyton/cloud-computing/blob/main/project/README.md#33-preguntas-de-defensa). Las preguntas se reformulan para el ensayo. Las respuestas y las evidencias corresponden a nuestra implementación y quedan para revisión grupal.

## Arquitectura · 1 a 5

### 1. ¿Por qué dar a cada bodega una base de datos propia?

Cada bodega confirma sus movimientos en su PostgreSQL. Así mantiene autonomía y puede dimensionar su almacenamiento por separado. La contrapartida es coordinar operaciones y consultas que cruzan bodegas. [Referencia](fases/fase-4.md)

### 2. ¿Por qué evitar una sola base operacional para todas las bodegas?

Una base compartida simplificaría las consultas y transacciones globales, pero concentraría el tráfico y ampliaría el impacto de fallos y cambios de esquema. La base central conserva proyecciones y estados de transferencias. [Referencia](architecture.md)

### 3. ¿Qué ve el usuario si una bodega queda inaccesible?

Las bodegas sanas continúan operando. CQRS conserva el último dato y marca la bodega como `stale` tras el umbral de heartbeat de 90 segundos. Fan-out puede responder con un resultado parcial. [Referencia](fases/fase-7.md)

### 4. ¿Cómo aumentar capacidad solo en la bodega con más demanda?

Agregar réplicas de su API detrás de nginx y medir latencia, errores y saturación de PostgreSQL. En WH-002, las réplicas comparten PostgreSQL y Redis, por lo que un cuello de botella de datos requiere otro ajuste. La ganancia hay que medirla: en F5, una réplica dio 383 req/s y tres dieron 884 req/s, pero la réplica única ya devolvía 504. J-09, con 200 usuarios, no mostró diferencia (963 frente a 995 req/s) y Locust estaba cerca de saturar un núcleo. [Referencia](fases/fase-5.md)

### 5. ¿Cómo se limita el impacto de un fallo local sobre las demás bodegas?

Se aíslan API, base y caché por bodega. El outbox desacopla escrituras locales del broker y los timeouts acotan esperas remotas. Las pruebas de carga desigual mostraron cero errores en WH-001 y WH-003 durante el colapso de WH-002. [Referencia](load-testing.md)

## Redis · 6 a 10

### 6. ¿Qué aporta Redis a las lecturas de inventario?

Cache Aside evita repetir consultas a PostgreSQL cuando varios clientes piden el mismo SKU. Redis reduce latencia y carga mientras PostgreSQL conserva el estado de referencia. En J-09, con la misma carga, Redis activado dio 785,7 req/s y P95 de 240 ms, frente a 468,9 req/s y 550 ms sin Redis. [Referencia](adr/0008-cache-aside-con-redis.md)

### 7. ¿Cómo responde la API durante una caída de Redis?

Lee directamente PostgreSQL y devuelve `X-Cache: BYPASS`. En la prueba F10 mantuvo HTTP 200 con mayor latencia. [Referencia](fases/fase-10.md)

### 8. ¿Cuándo y cómo se invalida una entrada de caché?

La API invalida la entrada afectada después del commit. Una lectura concurrente puede repoblarla con una versión anterior, por lo que el TTL acota cuánto permanece esa entrada. [Referencia](adr/0008-cache-aside-con-redis.md)

### 9. ¿Qué significa que una lectura tenga un cache miss?

Redis no tiene una entrada utilizable para la clave. La API consulta PostgreSQL y, si la caché está disponible, guarda la respuesta con TTL para lecturas posteriores. [Referencia](adr/0008-cache-aside-con-redis.md)

### 10. ¿Qué riesgo introduce una entrada obsoleta?

La lectura puede mostrar una cantidad diferente de la confirmada tras un movimiento. Las escrituras verifican existencias contra PostgreSQL dentro de una transacción y la invalidación con TTL reduce la ventana de discrepancia. El TTL documentado es de 30 segundos; uno más corto aumenta los misses y la carga en PostgreSQL. [Referencia](adr/0008-cache-aside-con-redis.md)

## RabbitMQ · 11 a 15

### 11. ¿Qué aporta un broker al intercambio de eventos?

RabbitMQ permite que central y workers consuman a su ritmo, con enrutamiento por evento o destino. El outbox retiene publicaciones pendientes si el broker está caído. A cambio aparecen colas, retrasos y duplicados posibles. [Referencia](adr/0005-topologia-rabbitmq.md)

### 12. ¿Cómo cambia el flujo entre procesamiento síncrono y asíncrono?

En el síncrono el cliente espera el resultado de la operación. En el asíncrono se confirma la aceptación y un worker continúa el trabajo. La API puede confirmar el movimiento local antes de que la proyección central refleje el cambio. [Referencia](adr/0006-patron-outbox.md)

### 13. ¿Qué ocurre con los mensajes si se detiene un worker?

Los mensajes pendientes permanecen en la cola durable. Una entrega sin confirmación puede volver a entregarse. D-06 comprobó que la proyección retomó el procesamiento al recuperar el consumidor. [Referencia](evidencias/fase-10/caso-3.txt)

### 14. ¿Para qué sirve una Dead Letter Queue?

Conserva mensajes que fallaron de forma permanente o agotaron sus reintentos, junto con información para diagnosticarlos. Así se puede inspeccionarlos o reprocesarlos sin bloquear el flujo principal. [Referencia](adr/0015-reintentos-dlq-idempotencia.md)

### 15. ¿Cómo se evita repetir efectos ante una entrega duplicada?

El consumidor registra el identificador del mensaje en la misma transacción que aplica el efecto. Si vuelve a llegar, confirma la entrega sin repetir el movimiento. La proyección también descarta versiones antiguas. [Referencia](adr/0020-idempotencia-comandos-bodega.md)

## Distribución · 16 a 20

### 16. ¿Por qué la transferencia cruza límites transaccionales?

Reserva, envío y recepción afectan a dos PostgreSQL independientes. Cada bodega confirma sus cambios localmente y el orquestador coordina su avance mediante comandos y resultados. [Referencia](adr/0013-saga-orquestada.md)

### 17. ¿En qué consiste una Saga y cómo se usa aquí?

Una Saga encadena transacciones locales y define compensaciones para fallos. El orquestador central persiste el estado, emite comandos y puede retomar el flujo después de reiniciar. [Referencia](adr/0013-saga-orquestada.md)

### 18. ¿Cómo funciona una compensación en una transferencia?

Es una nueva operación de negocio que compensa un paso confirmado. Por ejemplo, si el destino rechaza la recepción después del envío, se ordena devolver inventario al origen con `RETURN_STOCK`. [Referencia](fases/fase-6.md)

### 19. ¿Qué implica la consistencia eventual?

Entre el commit local y el procesamiento del evento, la vista central puede mostrar el estado anterior. Cuando se entregan y procesan los eventos pendientes, la proyección converge a la última versión de cada SKU y bodega. [Referencia](adr/0012-proyeccion-cqrs.md)

### 20. ¿Qué hace la Saga si el destino guarda silencio tras el envío?

La transferencia queda `DESTINATION_PENDING`. La central alerta tras cinco minutos y puede completar al recibir la confirmación. Un rechazo definitivo habilita la compensación. Compensar solo por silencio podría duplicar unidades en tránsito. [Referencia](adr/0013-saga-orquestada.md)

## CQRS · 21 a 24

### 21. ¿Para qué construir un modelo de lectura central?

Para consultar inventario consolidado con una sola lectura y separar el rendimiento de las consultas globales del de las escrituras operacionales de cada bodega. [Referencia](adr/0012-proyeccion-cqrs.md)

### 22. ¿Qué costo tiene consultar todas las bodegas en cada solicitud?

Fan-out multiplica llamadas y la latencia depende de las APIs lentas o inaccesibles. En la prueba de F7, durante la operación normal CQRS obtuvo P95 de 200 ms frente a 580 ms de Fan-out, y 98,5 frente a 42,6 req/s. Con una bodega inaccesible, CQRS respondió 6.283 de 6.283 solicitudes y Fan-out solo 8 de 1.386 (0,58 %). [Referencia](fases/fase-7.md)

### 23. ¿Qué significa que el inventario de la vista global esté atrasado?

La central todavía muestra la última versión aplicada. El retraso de proyección mide la demora de procesamiento y el heartbeat indica actividad de la bodega. Una vista puede responder HTTP 200 mientras conserva datos anteriores. [Referencia](adr/0012-proyeccion-cqrs.md)

### 24. ¿Qué ventaja da proyectar el inventario a partir de eventos?

El worker actualiza las filas por SKU y bodega según la versión del evento. Así mantiene una representación optimizada para consultas globales sin cargar las bases operacionales y evita que un evento antiguo sobrescriba el dato actual. [Referencia](fases/fase-7.md)

## Cloud · 25 a 29

### 25. ¿Qué papel cumple EC2 en el despliegue?

La instancia ejecuta los contenedores de la plataforma mediante Docker Compose. Permite reutilizar el empaquetado local y concentrar la operación del laboratorio en un host, con capacidad y disponibilidad ligadas a esa instancia. [Referencia](aws.md)

### 26. ¿Cómo facilita ECR el despliegue de los contenedores?

ECR almacena las imágenes construidas para que EC2 las descargue con su identidad autorizada. Esto separa la construcción de la ejecución y permite desplegar versiones identificables. [Referencia](aws.md)

### 27. ¿Qué cambia al usar RDS para PostgreSQL en lugar de un contenedor local?

Ambos ofrecen PostgreSQL. En el laboratorio, RDS hospeda WH-001 como servicio administrado con su endpoint y reglas de acceso. En local, Compose arranca el contenedor y el equipo gestiona sus volúmenes e inicialización. [Referencia](aws.md)

### 28. ¿Por qué guardar los reportes en S3?

S3 conserva reportes y metadatos como objetos independientes de EC2. El batch escribe un resumen diario y el evento de creación dispara la validación. MinIO permite probar el contrato de objetos en local. [Referencia](fases/fase-9.md)

### 29. ¿Cuándo encaja Lambda en el procesamiento de reportes?

Cuando un evento de S3 requiere una validación breve y acotada. El worker sirve para consumo continuo y el batch para agrupar trabajo por horario. Lambda evita mantener un proceso activo para cada espera entre reportes. [Referencia](fases/fase-9.md)

## Observabilidad · 30 a 33

### 30. ¿Cómo se rastrea una operación a través de varios servicios?

Propagar `X-Correlation-ID` desde el POST inicial hacia comandos, respuestas y logs. Buscar el mismo ID y verificar el estado final consultando el historial de la transferencia. [Referencia](evidencias/fase-11/traza-transferencia-saga.json)

### 31. ¿Qué campos permiten que un log sirva para diagnosticar un fallo?

Fecha y hora, nivel, servicio, bodega cuando corresponda, acción, identificador de correlación, resultado y duración. En un error se agrega su causa. Conviene evitar claves de API y credenciales. [Referencia](events.md)

### 32. ¿Cómo reconocer una cola que no alcanza a drenar?

Observar si los mensajes listos crecen sostenidamente y si la tasa de entrada supera la de confirmación. Revisar entregas sin confirmar, número de consumidores, retraso y errores para distinguir acumulación de un consumidor atascado. [Referencia](fases/fase-11.md)

### 33. ¿Cómo acotar la causa de una consulta lenta?

Identificar el endpoint por P95/P99 y buscar una solicitud lenta por correlación. Comparar tiempo de API, caché, pool y carga de PostgreSQL. Si la demora está en SQL, revisar su plan con `EXPLAIN` y comprobar índices, filas y bloqueos. [Referencia](fases/fase-11.md)

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

Las filas de F2 y F5 son las corridas históricas de cada fase. J-09
repitió esas comparaciones con otra carga y configuración, y sus
cifras no coinciden con las de la tabla:

| Experimento J-09 | Sin la mejora | Con la mejora |
| --- | ---: | ---: |
| Redis, RPS | 468.9 sin Redis | 785.7 con Redis |
| Redis, P95 | 550 ms sin Redis | 240 ms con Redis |
| WH-002, RPS | 963.0 con 1 instancia | 995.1 con 3 instancias |
| WH-002, P95 | 240 ms con 1 instancia | 320 ms con 3 instancias |

La mejora de Redis se confirma. La de pasar de una a tres réplicas no
se reproduce en J-09: con 200 usuarios no hubo diferencia y Locust
pudo limitar el resultado, y la corrida histórica de F5 partía de una
réplica que ya devolvía 504. Al citar F5 en la defensa, indicar esas
condiciones. Detalle en
[load-testing.md](load-testing.md) y
[evidencias/fase-11/README.md](evidencias/fase-11/README.md).

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

J-09 aporta pruebas de carga desigual y progresiva en tres bodegas. Para validar 100 bodegas quedan por medir la saturación del broker, el crecimiento de la proyección y la recuperación a esa escala.

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
