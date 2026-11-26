# ADR-0017: Lambda fuera de la VPC

- Estado: aceptado
- Fecha: 2026-11-25
- Autor: Julian (tarea S-08, issue #29; responsable asignado: Santiago)

## Contexto

La Lambda `report-validator` se dispara cuando se crea un `reports/**/*.json` en S3. Solo necesita hablar con dos cosas: S3 (leer el reporte y escribir en `metadata/`) y la API de la central (`POST /internal/reports`), que corre en la EC2 y ya expone sus puertos de API para la demo. Hay que decidir si la función va dentro de la VPC o fuera.

## Alternativas

| Alternativa | A favor | En contra |
| --- | --- | --- |
| **Fuera de la VPC** (sin `vpc_config`) | Acceso directo a S3 y a Internet; sin recursos de red extra; arranque en frío más corto | La central debe ser alcanzable por su IP pública; la función no llega a recursos privados |
| Dentro de la VPC | Puede llamar a la central o a RDS por IP privada | Sin salida a Internet por defecto: hace falta un NAT Gateway (con costo por hora) o endpoints de VPC para S3; más piezas que crear y destruir en cada sesión del laboratorio |

## Decisión

La Lambda no se asocia a ninguna VPC. Llama a la central por su dirección pública (`CENTRAL_API_URL`) con `X-API-Key` y no accede a RDS: la central es la única que escribe en su base.

## Consecuencias

- El puerto de la API central debe estar abierto para la Lambda; la clave de API es lo único que protege `POST /internal/reports`.
- `CENTRAL_API_KEY` viaja como variable de entorno de la función: queda en el estado de Terraform y es visible en la consola de AWS. Es aceptable en el laboratorio; en producción iría en un gestor de secretos.
- Si en el futuro la central solo fuera privada, habría que meter la Lambda en la VPC y pagar el NAT o los endpoints.
- La función evita el bucle de invocación escribiendo sus resultados en `metadata/` y filtrando por prefijo y sufijo (`reports/`, `.json`) tanto en la notificación de S3 como en el código.
