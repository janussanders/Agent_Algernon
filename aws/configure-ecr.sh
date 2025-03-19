#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source utilities and configs
source "${SCRIPT_DIR}/utils.sh"
source "${SCRIPT_DIR}/config.sh"

# Check if deployment mode is provided
if [ -z "$1" ]; then
    log_error "Deployment mode not provided"
    log_warning "Usage: $0 <dev|prod>"
    exit 1
fi

DEPLOY_MODE="$1"
export DEPLOY_MODE

log_warning "Configuring ECR for ${DEPLOY_MODE} environment"

# Verify AWS credentials
log_warning "Verifying AWS credentials..."
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "AWS credentials are invalid or not properly configured"
    exit 1
fi

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "${AWS_ACCOUNT_ID}" ]; then
    log_error "Failed to get AWS account ID"
    exit 1
fi

# Set repository name
REPO_NAME="algernon"
IMAGE_TAG="rag-agent-${DEPLOY_MODE}"

# Create ECR repository if it doesn't exist
log_warning "Creating ECR repository: ${REPO_NAME}"
aws ecr create-repository \
    --repository-name "${REPO_NAME}" \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability MUTABLE \
    --output json || true

# Authenticate with ECR
log_warning "Authenticating with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

if [ $? -eq 0 ]; then
    log_success "Successfully authenticated with ECR"
else
    log_error "Failed to authenticate with ECR"
    exit 1
fi

# Clean up existing images with the same tag
log_warning "Cleaning up existing images with tag ${IMAGE_TAG}..."
aws ecr batch-delete-image \
    --repository-name "${REPO_NAME}" \
    --image-ids "imageTag=${IMAGE_TAG}" \
    --output json || true

# Build the Docker image
log_warning "Building combined image for ${DEPLOY_MODE}..."
docker build \
    --no-cache \
    --pull \
    --platform linux/amd64 \
    -t "${REPO_NAME}:${IMAGE_TAG}" \
    -f "${SCRIPT_DIR}/docker/Dockerfile.combined" \
    "${SCRIPT_DIR}/.."

if [ $? -eq 0 ]; then
    log_success "Docker image built successfully"
else
    log_error "Failed to build Docker image"
    exit 1
fi

# Tag and push the image to ECR
log_warning "Tagging and pushing image to ECR..."
docker tag "${REPO_NAME}:${IMAGE_TAG}" "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}"
docker push "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}"

if [ $? -eq 0 ]; then
    log_success "Image pushed successfully to ECR"
else
    log_error "Failed to push image to ECR"
    exit 1
fi

# Clean up untagged images
log_warning "Cleaning up untagged images..."
aws ecr batch-delete-image \
    --repository-name "${REPO_NAME}" \
    --image-ids "$(aws ecr describe-images --repository-name "${REPO_NAME}" --filter "tagStatus=UNTAGGED" --query "imageDetails[*].imageDigest" --output text)" \
    --output json || true

# Verify the image in ECR
log_warning "Verifying image in ECR..."
MAX_RETRIES=5
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    IMAGE_EXISTS=$(aws ecr describe-images \
        --repository-name "${REPO_NAME}" \
        --filter "tagStatus=TAGGED" \
        --query "imageDetails[?contains(imageTags, '${IMAGE_TAG}')].imageSizeInBytes" \
        --output text)
    
    if [ ! -z "${IMAGE_EXISTS}" ]; then
        log_success "Image verified in ECR with size: $((IMAGE_EXISTS/1024/1024))MB"
        exit 0
    fi
    
    log_warning "Image not found in ECR, retrying... (Attempt $((RETRY_COUNT + 1))/${MAX_RETRIES})"
    sleep 10
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

log_error "Failed to verify image in ECR after ${MAX_RETRIES} attempts"
exit 1 