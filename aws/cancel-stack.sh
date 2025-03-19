#!/bin/bash

# Source configuration
source "$(dirname "$0")/config.sh"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Helper functions
log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_warning() { echo -e "${YELLOW}! $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}" >&2; }

# Check if stack exists first
if ! aws cloudformation describe-stacks --stack-name algernon >/dev/null 2>&1; then
    log_warning "Stack 'algernon' does not exist"
    exit 0
fi

# First, check what resources are failing to delete
echo "Checking stack resources..."
aws cloudformation list-stack-resources --stack-name algernon \
    --query 'StackResourceSummaries[?ResourceStatus==`DELETE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
    --output table

# Check if service exists first
SERVICE_ARN=$(aws apprunner list-services \
    --region "${AWS_REGION}" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
    --output text)

if [ -z "${SERVICE_ARN}" ]; then
    log_warning "Service '${SERVICE_NAME}' does not exist"
    exit 0
fi

# Force delete App Runner service if it exists
log_warning "Cleaning up App Runner service..."
if [ -n "${SERVICE_ARN}" ]; then
    aws apprunner delete-service \
        --region "${AWS_REGION}" \
        --service-arn "${SERVICE_ARN}"
fi

# Wait for service deletion
log_warning "Waiting for service deletion..."
while true; do
    STATUS=$(aws apprunner describe-service \
        --region "${AWS_REGION}" \
        --service-arn "${SERVICE_ARN}" \
        --query 'Service.Status' \
        --output text 2>/dev/null || echo "DELETED")
    
    if [ "${STATUS}" = "DELETED" ]; then
        log_success "Service deletion complete"
        break
    elif [ "${STATUS}" = "OPERATION_FAILED" ]; then
        log_error "Service deletion failed"
        exit 1
    fi
    
    echo -n "."
    sleep 10
done

echo "Attempting stack deletion..."
aws cloudformation delete-stack --stack-name algernon

log_warning "Waiting for stack deletion..."
# Wait with a timeout
timeout 300 aws cloudformation wait stack-delete-complete --stack-name algernon

case $? in
    0)
        log_success "Stack deletion complete"
        ;;
    124)
        log_error "Stack deletion timed out after 5 minutes"
        ;;
    *)
        log_warning "Stack no longer exists"
        ;;
esac 