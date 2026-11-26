#!/usr/bin/env bash
# Sube a s3://<bucket>/deploy/ lo que la EC2 descarga al arrancar (S-09):
# docker-compose.yaml, init-rds.sh y los SQL de las bases (schema, migraciones y seeds).
# Uso: scripts/aws-bundle.sh <bucket>
set -euo pipefail

cd "$(dirname "$0")/.."
BUCKET=${1:?uso: scripts/aws-bundle.sh <bucket>}
DEST="s3://$BUCKET/deploy"
REGION=${AWS_REGION:-us-east-1}

aws s3 cp infrastructure/aws/docker-compose.yaml "$DEST/docker-compose.yaml" --region "$REGION"
aws s3 cp infrastructure/aws/init-rds.sh "$DEST/init-rds.sh" --region "$REGION"
aws s3 sync infrastructure/sql/warehouse "$DEST/sql/warehouse" --delete --region "$REGION"
aws s3 cp infrastructure/sql/central/schema.sql "$DEST/sql/central/schema.sql" --region "$REGION"
echo "Paquete de despliegue en $DEST/"
