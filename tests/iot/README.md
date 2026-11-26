# Validación de D-07

`bash tests/iot/smoke.sh` levanta un proyecto Compose aislado llamado `d07-iot`, ejecuta 10 sensores durante 8 segundos con duplicados, reordenamiento y una interrupción de red, verifica los conteos en PostgreSQL y guarda el resumen en `docs/evidencias/fase-12/simulacion-smoke.json`. Al finalizar elimina los contenedores del proyecto aislado y conserva sus volúmenes para poder inspeccionarlos.

La aceptación definida por el plan dura diez minutos: `bash scripts/iot/run-acceptance.sh`. Se puede cambiar la duración para depuración con `SIM_DURATION_SECONDS`, pero la evidencia válida para el requisito es la ejecución por defecto de 600 segundos. El reporte se escribe en `docs/evidencias/fase-12/simulacion-10min.json`.

Las pruebas aisladas usan puertos 26772/26773 para RabbitMQ, 21883 para MQTT y 29102–29105 para métricas, por lo que pueden ejecutarse mientras el Compose normal está activo. Requiere Docker Compose v2 y Bash.
