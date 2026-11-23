# Resultado del experimento de caché (100 usuarios, 2m, mismo SKU, espera máx. 0.05 s)

| Métrica | Con caché | Sin caché |
| --- | --- | --- |
| Peticiones | 213100 | 1611 |
| Fallos | 0 | 82 |
| RPS | 1789.0 | 17.6 |
| P50 (ms) | 27 | 58 |
| P95 (ms) | 56 | 30000 |
| P99 (ms) | 73 | 30000 |
| CPU API (media %) | 105 | 3 |
| CPU PostgreSQL (media %) | 2 | 1 |
| CPU Redis (media %) | 3 | 1 |
| Transacciones en PostgreSQL (`xact_commit`) | 540 | 52 |
| Tasa de hit | 100.0 % | n/a |
