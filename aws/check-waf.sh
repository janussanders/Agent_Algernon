#!/bin/bash

# Source configuration
source "$(dirname "$0")/config.sh"

# List Web ACLs
log_warning "Checking Web ACLs in region ${AWS_REGION}..."
WEB_ACLS=$(aws wafv2 list-web-acls \
    --scope REGIONAL \
    --region "${AWS_REGION}" \
    --query 'WebACLs[*].[Name,ARN]' \
    --output text)

if [ -z "${WEB_ACLS}" ]; then
    log_warning "No Web ACLs found in region ${AWS_REGION}"
else
    log_success "Found Web ACLs:"
    echo "${WEB_ACLS}"
fi

# Check Web ACL associations
log_warning "Checking Web ACL associations for service: ${SERVICE_NAME}..."
SERVICE_ARN=$(aws apprunner list-services \
    --region "${AWS_REGION}" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
    --output text)

if [ -n "${SERVICE_ARN}" ]; then
    ASSOCIATIONS=$(aws wafv2 list-web-acl-associations \
        --scope REGIONAL \
        --region "${AWS_REGION}" \
        --query "WebACLAssociations[?ResourceArn=='${SERVICE_ARN}']" \
        --output text)
    
    if [ -n "${ASSOCIATIONS}" ]; then
        log_warning "Found Web ACL associations for service:"
        echo "${ASSOCIATIONS}"
    else
        log_success "No Web ACL associations found for service"
    fi
else
    log_warning "Service ${SERVICE_NAME} not found"
fi 