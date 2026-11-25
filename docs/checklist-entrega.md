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
- [ ] Completar y revisar los 19 ADR.
- [ ] Resolver correspondencia del ADR-0004.
- [ ] Resolver numeracion duplicada del ADR-0014.
- [ ] Documentar las fases 1 a 12 con evidencias.
- [ ] Consolidar las 33 respuestas de la defensa.
- [ ] Contrastar las preguntas con el enunciado original.
- [ ] Actualizar README principal con ejecucion,
  profiles y demo.

## Integracion pendiente

- [ ] E-01: integracion de documentacion.
- [ ] E-04: proyeccion CQRS.
- [ ] E-05: fan-out y comparacion experimental.
- [ ] E-06: Saga e integracion con J-07.
- [ ] E-07: informe final y pruebas de resiliencia.
- [ ] E-08: revision de arquitectura y defensa.
- [ ] Verificar CI y aprobaciones correspondientes.

## Ensayo de la defensa

Duracion prevista: 45 minutos.

Cada integrante debe responder preguntas de un
bloque diferente al de su responsabilidad principal.

- [ ] Santiago: bloque de otro integrante.
- [ ] Julian: bloque de otro integrante.
- [ ] David: bloque de otro integrante.
- [ ] Esteban: bloque de otro integrante.
- [ ] Revisar errores y dudas del ensayo.
- [ ] Validar el guion de demostracion.

## Liberacion final

- [ ] Integrar los cambios aprobados en main.
- [ ] Verificar funcionamiento desde un clon limpio.
- [ ] Revisar evidencias del despliegue AWS.
- [ ] Destruir recursos AWS despues de las pruebas.
- [ ] Crear el tag v1.0 sobre main validado.

No crear el tag mientras existan bloqueos de entrega.

## Observaciones

Este checklist distingue los borradores documentales
de los entregables completamente verificados.

La existencia de archivos no garantiza que una fase
este integrada o funcione correctamente.

Los estados deben actualizarse con evidencia real
durante la revision final del equipo.
