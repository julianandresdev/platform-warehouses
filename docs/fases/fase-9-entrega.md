\### Validación de AWS Lambda y EventBridge



Se implementó un flujo de procesamiento serverless que se activa mediante eventos `ObjectCreated` de Amazon S3.



La función `warehouse-platform-export-handler` lee los reportes JSON, valida su estructura, transforma los datos y publica eventos `InventoryReportCreated` en Amazon EventBridge.



\*\*Pruebas realizadas:\*\*

\- Cinco pruebas unitarias ejecutadas correctamente.

\- Procesamiento real de un reporte JSON válido: `processed = 1`, `rejected = 0`.

\- Rechazo real de un reporte JSON inválido: `processed = 0`, `rejected = 1`.

\- Publicación de eventos en EventBridge confirmada mediante los registros de Lambda en CloudWatch.

\- Regla `warehouse-platform-report-created` creada y habilitada.



\*\*Limitación del entorno AWS Academy:\*\*



La política IAM `voc-cancel-cred` deniega explícitamente las operaciones `events:PutTargets` y `events:ListTargetsByRule`.



Por esta restricción no fue posible asociar ni verificar un destino de CloudWatch Logs para la regla de EventBridge. Por tanto, la publicación de eventos está comprobada, pero su entrega a un consumidor no pudo verificarse.



La limitación corresponde a permisos del entorno académico y no a un fallo observado en la validación o publicación realizada por Lambda.

