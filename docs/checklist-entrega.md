# Checklist de entrega - Warehouse Cloud Platform

Fecha de revision: 25 de noviembre de 2026.

Estado: Pendiente de integracion y validacion final.

## Entregables obligatorios

- [ ] Entregable 1: Diagrama de arquitectura final.
  Borrador preparado en docs/architecture.md.
  Pendiente de revision y renderizacion en GitHub.

- [ ] Entregable 2: Warehouse API, Central API,
  workers y procesamiento de eventos.
  Pendiente de validacion integrada.

- [ ] Entregable 3: Dockerfiles y Docker Compose.
  Verificar make up desde un clon limpio.

- [ ] Entregable 4: schema.sql, seed.sql y migrations.
  Verificar esquemas y datos iniciales.

- [ ] Entregable 5: docs/events.md completo.
  Verificar contratos de eventos y comandos.

- [ ] Entregable 6: docs/aws.md con evidencia
  de EC2, ECR, RDS, S3 y Lambda.

- [ ] Entregable 7: Terraform.
  Verificar reconstruccion de infraestructura.

- [ ] Entregable 8: Evidencias de pruebas unitarias,
  integracion, carga, fallos y recuperacion.

## Documentacion

- [x] Borrador del diagrama de arquitectura.
- [x] Indice consolidado de ADR disponibles.
- [x] ADR-0010 sobre autenticacion mediante API Key.
- [x] Borrador de preguntas 16 a 24.
- [x] Borrador de la pregunta final: 100 bodegas.
- [x] Enlazar los 19 ADR previstos.
- [ ] Revisar los borradores de ADR con sus responsables.
- [x] Índice actualizado al tema real del ADR-0004 (concurrencia).
- [x] Idempotencia de comandos identificada como ADR-0020.
- [x] Contrato de lectura por API verificado en ADR-0014 y en el batch diario.
- [ ] Documentar las fases 1 a 12 con evidencias.
- [x] Preparar 33 respuestas de ensayo para revisión.
- [ ] Validar las respuestas de cada bloque con sus responsables.
- [ ] Contrastar las preguntas con el enunciado original.
- [x] README principal actualizado con ejecución, perfil de carga y enlaces de demo.

## Integracion pendiente

- [x] E-01: documentación integrada en main (PR #57).
- [x] E-04: proyección CQRS integrada en main (PR #54).
- [x] E-05: fan-out integrado en main a través de E-04 (PR #55 y #54).
- [x] E-06: Saga y worker de bodega integrados en main (PR #56 y #59).
- [x] E-07: informe consolidado con las evidencias de D-06 y J-09.
- [ ] Revisión final del informe E-07 por Julian.
- [x] E-08: arquitectura y guía de defensa integradas en main (PR #61).
- [ ] Revisión grupal de arquitectura y defensa.
- [ ] Verificar CI y aprobaciones correspondientes.

## Ensayo de la defensa

Duración prevista de 45 minutos. La fecha queda por acordar con el equipo.

| Minutos | Actividad |
| --- | --- |
| 0–5 | Abrir la arquitectura y comprobar el entorno de la demo. |
| 5–29 | Cuatro rondas de seis minutos. Cada integrante responde dos preguntas de otro bloque y muestra una evidencia. |
| 29–39 | Ejecutar la demo de movimiento, transferencia y recuperación. |
| 39–45 | Registrar respuestas por corregir y responsables. |

Cada integrante debe responder preguntas de un
bloque diferente al de su responsabilidad principal.

- [ ] Santiago: Redis.
- [ ] Julian: RabbitMQ.
- [ ] David: Distribución y CQRS.
- [ ] Esteban: Cloud.
- [ ] Revisar errores y dudas del ensayo.
- [ ] Validar el guion de demostracion.

## Liberacion final

- [ ] Integrar los cambios aprobados en main.
- [ ] Verificar funcionamiento desde un clon limpio.
- [ ] Revisar evidencias del despliegue AWS.
- [x] Destrucción de recursos tras el ensayo AWS del 26 de noviembre, documentada en el PR #74.
- [ ] Crear el tag v1.0 sobre main validado.

No crear el tag mientras existan bloqueos de entrega.

## Observaciones

Este checklist distingue los borradores documentales
de los entregables completamente verificados.

La existencia de archivos no garantiza que una fase
este integrada o funcione correctamente.

Los estados deben actualizarse con evidencia real
durante la revision final del equipo.
