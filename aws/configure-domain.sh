#!/bin/bash

# Source configuration and utilities
source "$(dirname "$0")/utils.sh"
source "$(dirname "$0")/config.sh"

# Check if deployment mode is provided
if [ -z "$1" ]; then
    log_error "Deployment mode not provided"
    echo "Usage: $0 <dev|prod>"
    exit 1
fi

# Set deployment mode
DEPLOY_MODE="$1"

# Validate deployment mode
case "${DEPLOY_MODE}" in
    "dev"|"prod")
        log_warning "Configuring domain in ${DEPLOY_MODE} mode"
        ;;
    *)
        log_error "Invalid deployment mode '${DEPLOY_MODE}'"
        echo "Usage: $0 <dev|prod>"
        exit 1
        ;;
esac

# Wait for service to be ready
log_warning "Waiting for services to be ready..."
SERVICE_ARN=$(aws apprunner list-services \
    --query "ServiceSummaryList[?ServiceName=='algernon-${DEPLOY_MODE}-rag'].ServiceArn" \
    --output text)

if [ -z "${SERVICE_ARN}" ] || [ "${SERVICE_ARN}" = "None" ]; then
    log_error "RAG service not found: algernon-${DEPLOY_MODE}-rag"
    exit 1
fi

# Configure custom domain
log_warning "Configuring custom domain for service: ${SERVICE_ARN}"
if ! aws apprunner associate-custom-domain \
    --service-arn "${SERVICE_ARN}" \
    --domain-name "${DOMAIN_NAME}" \
    --enable-www-subdomain; then
    log_error "Failed to configure custom domain"
    exit 1
fi

log_success "Domain configuration completed" 