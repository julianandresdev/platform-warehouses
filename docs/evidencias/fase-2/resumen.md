# Resultado del experimento de caché (100 usuarios, 2m, mismo SKU, espera máx. 0.05 s)

| Métrica | Con caché | Sin caché |
| --- | --- | --- |
| Peticiones | 213907 | 98566 |
| Fallos | 0 | 0 |
| RPS | 1795.7 | 827.4 |
| P50 (ms) | 27 | 92 |
| P95 (ms) | 52 | 130 |
| P99 (ms) | 66 | 160 |
| CPU API (media %) | 104 | 111 |
| CPU PostgreSQL (media %) | 1 | 18 |
| CPU Redis (media %) | 2 | 0 |
| Transacciones en PostgreSQL (`xact_commit`) | 5016 | 99094 |
| Tasa de hit | 100.0 % | n/a |
