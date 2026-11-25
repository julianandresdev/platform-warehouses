# ADR-0010 - Autenticacion mediante API Key

## Estado

Decision del plan implementada en la plataforma central.
Documento pendiente de revision.

## Contexto

La plataforma necesita proteger los endpoints de las
bodegas y de la central sin implementar un sistema
completo de usuarios y operadores.

## Alternativas

1. Endpoints sin autenticacion.
2. Autenticacion mediante API Key.
3. Autenticacion mediante JWT u OAuth 2.0.

## Decision

Utilizar el encabezado HTTP X-API-Key para autenticar
las solicitudes a los endpoints protegidos.

Las claves se configuran mediante variables de entorno.
Las solicitudes sin una clave valida reciben HTTP 401.

Los endpoints de salud pueden permanecer accesibles
para las comprobaciones de disponibilidad.

La gestion completa de usuarios, operadores y roles
queda fuera del alcance acordado del proyecto.

## Consecuencias

### Ventajas

- Implementacion sencilla.
- Proteccion de endpoints internos.
- Integracion entre servicios.
- Menor complejidad de desarrollo.

### Desventajas

- No identifica individualmente a cada usuario.
- Requiere administracion y rotacion de claves.
- Una clave comprometida permite accesos no autorizados.
- Requiere HTTPS y gestion segura de secretos en produccion.

## Validacion

En E-03 se verifico que una solicitud sin API Key
valida recibe HTTP 401 y que las solicitudes
autenticadas pueden acceder a los endpoints protegidos.
