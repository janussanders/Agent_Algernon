#!/bin/bash

# Check if DEPLOY_MODE is provided as argument
if [ -z "$1" ]; then
    echo "Usage: $0 <deploy_mode>"
    echo "Example: $0 dev"
    echo "Available modes: dev, prod, update"
    exit 1
fi

# Set deployment mode
export DEPLOY_MODE="$1"

# Source configuration
source "$(dirname "$0")/utils.sh"
source "$(dirname "$0")/config.sh"

# Set service name with deployment mode
SERVICE_NAME="algernon-${DEPLOY_MODE}"

log_warning "Checking for available log groups..."

# Get the actual log group path
ACTUAL_LOG_GROUP=$(aws logs describe-log-groups \
    --log-group-name-prefix "/aws/apprunner/${SERVICE_NAME}" \
    --query 'logGroups[0].logGroupName' \
    --output text)

if [ -z "$ACTUAL_LOG_GROUP" ] || [ "$ACTUAL_LOG_GROUP" = "None" ]; then
    log_warning "Available App Runner log groups:"
    aws logs describe-log-groups \
        --log-group-name-prefix "/aws/apprunner" \
        --query 'logGroups[*].[logGroupName,storedBytes]' \
        --output table
    log_error "No log group found for ${SERVICE_NAME}"
    exit 1
fi

log_warning "Found log group: ${ACTUAL_LOG_GROUP}"

log_warning "Deleting log group: ${ACTUAL_LOG_GROUP}"

# Delete the log group in background
(
    echo "Deleting log group ${ACTUAL_LOG_GROUP}..." > /tmp/clear_logs_status
    if aws logs delete-log-group --log-group-name "$ACTUAL_LOG_GROUP"; then
        echo "Successfully deleted log group ${ACTUAL_LOG_GROUP}" > /tmp/clear_logs_status
    else
        echo "Failed to delete log group ${ACTUAL_LOG_GROUP}" > /tmp/clear_logs_status
        exit 1
    fi
) &

# Show progress spinner
show_spinner $! "Deleting log group"

# Clean up status file
rm -f /tmp/clear_logs_status

log_success "Successfully deleted log group: ${ACTUAL_LOG_GROUP}" 