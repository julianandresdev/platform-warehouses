# Resultado del experimento de caché (100 usuarios, 1m, mismo SKU, espera máx. 0 s)

| Métrica | Con caché | Sin caché |
| --- | --- | --- |
| Peticiones | 75051 | 49730 |
| Fallos | 0 | 0 |
| RPS | 1270.8 | 842.0 |
| P50 (ms) | 75 | 120 |
| P95 (ms) | 110 | 150 |
| P99 (ms) | 130 | 180 |
| CPU API (media %) | 100 | 109 |
| CPU PostgreSQL (media %) | 3 | 17 |
| CPU Redis (media %) | 2 | 0 |
| Transacciones en PostgreSQL (`xact_commit`) | 5094 | 50228 |
| Tasa de hit | 99.9 % | n/a |
