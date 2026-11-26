# Escenarios de caos de Fase 10

Los scripts usan un proyecto de Compose aislado (`d06-chaos`) con las tres
bodegas y la central. El overlay de puertos evita interferir con los servicios
del Compose habitual. Se puede cambiar el proyecto con
`D06_COMPOSE_PROJECT` si ya existe uno con ese nombre.

Con Docker Compose y Bash disponibles desde la raíz del repositorio:

```bash
bash tests/chaos/run-all.sh
```

También se puede ejecutar un escenario individual, por ejemplo:

```bash
bash tests/chaos/caso-1-redis.sh
```

`run-all.sh` levanta el stack una vez, ejecuta los cinco escenarios y lo apaga
al terminar. Cada script individual también levanta y apaga el stack por sí
mismo. Los volúmenes de prueba se conservan para no borrar datos de forma
implícita; `D06_COMPOSE_PROJECT` permite separar ejecuciones. La salida de cada
escenario queda en `docs/evidencias/fase-10/caso-N.txt`.
