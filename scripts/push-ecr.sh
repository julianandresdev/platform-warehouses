#!/usr/bin/env bash
# Construye las imágenes para linux/amd64 (la EC2 es x86_64) y las sube a ECR (S-09).
# Requiere los repositorios ya creados (terraform apply -target=module.ecr) y las
# credenciales del Learner Lab en el perfil de AWS (AWS_PROFILE=lab).
# Uso: scripts/push-ecr.sh [tag]      (por defecto: latest)
set -euo pipefail

cd "$(dirname "$0")/.."
REGION=${AWS_REGION:-us-east-1}
TAG=${1:-latest}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

# repositorio:Dockerfile (contexto de build: services/)
for item in warehouse:warehouse-api/Dockerfile central:central/Dockerfile batch:batch/Dockerfile; do
  repo=${item%%:*}
  dockerfile=${item#*:}
  echo "== $repo ($dockerfile) -> $REGISTRY/$repo:$TAG"
  docker buildx build --platform linux/amd64 -f "services/$dockerfile" \
    -t "$REGISTRY/$repo:$TAG" --push services/
done

aws ecr describe-images --region "$REGION" --repository-name warehouse \
  --query 'imageDetails[].[imageTags[0],imageSizeInBytes]' --output text >/dev/null
echo "Imágenes subidas con la etiqueta $TAG"
