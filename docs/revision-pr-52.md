# Respuesta al review del PR #52

**Estado: correcciones documentales aplicadas; issues no cerrados.**

| Revisión | Acción |
|---|---|
| #1 Vinculación de issues | PR relacionado con #12, #27 y #29; ninguno se declara cerrado sin aceptación de sus criterios. |
| #2 Diferencias funcionales | ADR-0014 y ADR-0017 propuestos, no aprobados; se agregó implementación de soporte de contrato, pendiente de prueba de integración y aprobación. |
| #3 Terraform | `eventbridge.tf` incluye regla, destino y CloudWatch; `docs/aws.md` ahora detalla los módulos faltantes del #27. |
| #4 Evidencia Lambda | `lambda-cloudwatch.txt` se reemplaza por el registro real final, siempre que exista el archivo fuente. |
| #5 Documentación | Normalizados `fase-8.md` y `fase-9-entrega.md`; se preservan entregas extendidas como anexos. |
| #6 Rama desactualizada | Rebase pendiente del equipo; evitar force-push sin coordinación. |
| Menores | Import de `date` al inicio; valores específicos del laboratorio reemplazados por placeholders en `terraform.tfvars.example`. |

## Criterios pendientes

#12: API de bodega, CLI común, rutas de storage, PARTIAL, registro central, evidencia de dos ejecuciones. Responsable asignado en el issue: Julian.

#27: Módulos Terraform agregados como opt-in, faltan validación real de apply/destroy y arranque automático.

#29: Metadata, POST y correlation-ID añadidos en código; faltan pruebas reales de API central/MinIO y comparativa cuantitativa.

No afirmar que se aprobaron ADR, pruebas de despliegue nuevo ni integración HTTP de la central: no se han verificado.
