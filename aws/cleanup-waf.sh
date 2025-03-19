#!/bin/bash

# Source utilities first
source "$(dirname "$0")/utils.sh"

# Check if deployment mode is provided
if [ -z "$1" ]; then
    log_error "Deployment mode not provided"
    log_warning "Usage: $0 <dev|prod|update>"
    exit 1
fi

# Set deployment mode
export DEPLOY_MODE="$1"

# Validate deployment mode
case "${DEPLOY_MODE}" in
    dev|prod|update)
        log_warning "Deploying in ${DEPLOY_MODE} mode"
        ;;
    *)
        log_error "Invalid deployment mode '${DEPLOY_MODE}'"
        log_warning "Usage: $0 <dev|prod|update>"
        exit 1
        ;;
esac

# Now source config after DEPLOY_MODE is set
source "$(dirname "$0")/config.sh"

# Set deployment mode
DEPLOY_MODE="$1"

# Validate deployment mode
case "${DEPLOY_MODE}" in
    "dev"|"prod")
        log_warning "Removing WAF in ${DEPLOY_MODE} mode"
        ;;
    *)
        log_error "Invalid deployment mode '${DEPLOY_MODE}'"
        echo "Usage: $0 <dev|prod>"
        exit 1
        ;;
esac

source "$(dirname "$0")/config.sh"

# Find Web ACL
log_warning "Finding Web ACL..."
WEB_ACL_ARN=$(aws wafv2 list-web-acls \
    --scope REGIONAL \
    --query "WebACLs[?contains(Name, 'algernon')].ARN" \
    --output text)

if [ -n "${WEB_ACL_ARN}" ] && [ "${WEB_ACL_ARN}" != "None" ]; then
    log_warning "Found Web ACL: ${WEB_ACL_ARN}"
    
    # Remove associations
    log_warning "Removing Web ACL associations..."
    RESOURCES=$(aws wafv2 list-resources-for-web-acl \
        --web-acl-arn "${WEB_ACL_ARN}" \
        --resource-type APP_RUNNER_SERVICE \
        --output text)
    
    if [ -n "${RESOURCES}" ] && [ "${RESOURCES}" != "None" ]; then
        for RESOURCE in ${RESOURCES}; do
            log_warning "Disassociating resource: ${RESOURCE}"
            aws wafv2 disassociate-web-acl \
                --resource-arn "${RESOURCE}" \
                --resource-type APP_RUNNER_SERVICE
        done
    fi
    
    # Extract Web ACL ID from ARN
    WEB_ACL_ID=$(echo "${WEB_ACL_ARN}" | grep -o '[0-9a-f]\{8\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{4\}-[0-9a-f]\{12\}')
    
    if [ -n "${WEB_ACL_ID}" ]; then
        # Get lock token
        LOCK_TOKEN=$(aws wafv2 get-web-acl \
            --name "algernon-waf" \
            --scope REGIONAL \
            --id "${WEB_ACL_ID}" \
            --query 'LockToken' \
            --output text)
        
        if [ -n "${LOCK_TOKEN}" ] && [ "${LOCK_TOKEN}" != "None" ]; then
            log_warning "Deleting Web ACL..."
            aws wafv2 delete-web-acl \
                --name "algernon-waf" \
                --scope REGIONAL \
                --id "${WEB_ACL_ID}" \
                --lock-token "${LOCK_TOKEN}"
        fi
    fi
fi 

log_success "WAF cleanup completed"