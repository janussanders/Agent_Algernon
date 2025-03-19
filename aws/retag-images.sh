#!/bin/bash

# Source utilities and config
source "$(dirname "$0")/utils.sh"

# Check if deployment mode is provided
if [ -z "$1" ]; then
    echo "Error: Deployment mode not provided"
    echo "Usage: $0 <mode>"
    exit 1
fi

export DEPLOY_MODE="$1"

# Now source config.sh after DEPLOY_MODE is set
source "$(dirname "$0")/config.sh"

log_warning "Retagging images for ${DEPLOY_MODE}..."

# Re-tag Qdrant
if ! docker tag "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/qdrant:${DEPLOY_MODE}-amd64" \
                "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/qdrant:${DEPLOY_MODE}"; then
    log_error "Failed to retag Qdrant image"
    exit 1
fi

# Re-tag RAG app
if ! docker tag "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/rag-app:${DEPLOY_MODE}-amd64" \
                "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/rag-app:${DEPLOY_MODE}"; then
    log_error "Failed to retag RAG app image"
    exit 1
fi

# Push new tags
log_warning "Pushing new tags..."
if ! docker push "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/qdrant:${DEPLOY_MODE}"; then
    log_error "Failed to push Qdrant image"
    exit 1
fi

if ! docker push "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/rag-app:${DEPLOY_MODE}"; then
    log_error "Failed to push RAG app image"
    exit 1
fi

log_success "Successfully retagged and pushed images" 