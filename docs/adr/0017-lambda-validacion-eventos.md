# ADR-0017 — Validación de reportes con AWS Lambda fuera de la VPC

**Estado: propuesta pendiente de aprobación del equipo.**

## Contexto
El issue #29 exige metadatos S3, registro central HTTP autenticado y `correlation-id`. Se verificó un flujo alternativo S3 (`exports/`) → Lambda → EventBridge → CloudWatch, que no satisface todo el contrato del issue.

## Alternativas
1. Implementar exactamente el contrato: reportes en `reports/`, archivo en `metadata/reports/`, `POST /internal/reports` con API key, logging de correlation ID.
2. Publicar un evento EventBridge después de validar el JSON (estado actual).

## Decisión propuesta
Conservar EventBridge como integración complementaria y **agregar** el contrato del issue cuando la API central esté implementada y accesible. Evitar colocar Lambda en VPC sin necesidad: la conexión HTTPS con la API central requeriría una dirección alcanzable y permisos reales, no confirmados todavía.

## Consecuencias
La publicación EventBridge está probada, pero no sustituye la persistencia de metadatos ni el registro central. Se deben gestionar reintentos, idempotencia, secretos por variables seguras y protección contra bucles del trigger S3.
