#!/bin/bash

# Check if deployment mode is provided
if [ -z "$1" ]; then
    echo "Error: Please provide deployment mode (dev/prod)"
    exit 1
fi

# Set deployment mode
export DEPLOY_MODE="$1"

# Validate deployment mode
if [ "${DEPLOY_MODE}" != "dev" ] && [ "${DEPLOY_MODE}" != "prod" ]; then
    echo "Error: Invalid DEPLOY_MODE '${DEPLOY_MODE}'. Must be 'dev' or 'prod'"
    exit 1
fi

# Source configuration and utilities
source "$(dirname "$0")/utils.sh"
source "$(dirname "$0")/config.sh"

# Function to delete a security group rule
delete_security_group_rule() {
    local sg_id="$1"
    local rule_id="$2"
    local is_egress="$3"
    local max_attempts="$4"
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if [ "${is_egress}" = "True" ]; then
            log_warning "Revoking egress rule: ${rule_id} (Attempt ${attempt}/${max_attempts})"
            if aws ec2 revoke-security-group-egress \
                --group-id "${sg_id}" \
                --security-group-rule-ids "${rule_id}"; then
                return 0
            fi
        else
            log_warning "Revoking ingress rule: ${rule_id} (Attempt ${attempt}/${max_attempts})"
            if aws ec2 revoke-security-group-ingress \
                --group-id "${sg_id}" \
                --security-group-rule-ids "${rule_id}"; then
                return 0
            fi
        fi
        
        log_warning "Rule deletion failed, retrying..."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    log_error "Failed to delete rule ${rule_id} after ${max_attempts} attempts"
    return 1
}

# Function to check and handle security group dependencies
check_security_group_dependencies() {
    local sg_id="$1"
    local sg_name="$2"
    
    # Check for network interfaces
    log_warning "Checking network interface dependencies for ${sg_name}..."
    local eni_ids=$(aws ec2 describe-network-interfaces \
        --filters "Name=group-id,Values=${sg_id}" \
        --query 'NetworkInterfaces[*].[NetworkInterfaceId,InterfaceType]' \
        --output text)
    
    if [ -n "${eni_ids}" ]; then
        log_warning "Found network interfaces using security group ${sg_name}:"
        local has_non_vpc_endpoint=false
        
        while IFS=$'\t' read -r eni_id interface_type; do
            if [ -n "${eni_id}" ]; then
                # Get the interface details
                local eni_details=$(aws ec2 describe-network-interfaces \
                    --network-interface-ids "${eni_id}" \
                    --query 'NetworkInterfaces[0].[Description,Status,RequesterManaged,InterfaceType]' \
                    --output text)
                
                read -r description status requester_managed type <<< "${eni_details}"
                
                log_warning "  - ENI ${eni_id}: ${description} (Type: ${type}, Status: ${status}, Requester Managed: ${requester_managed})"
                
                # Skip VPC endpoint interfaces - these will be cleaned up by VPC cleanup
                if [[ "${type}" == "vpc_endpoint" ]] || [[ "${description}" == *"VPC Endpoint Interface"* ]]; then
                    log_warning "    Skipping VPC endpoint interface - will be cleaned up by VPC cleanup"
                    continue
                fi
                
                # If the interface is requester-managed by other AWS services, skip it
                if [ "${requester_managed}" = "true" ]; then
                    log_warning "    Skipping requester-managed interface - will be cleaned up by AWS"
                    continue
                fi
                
                # For non-managed interfaces that are "available", try to delete them
                if [ "${status}" = "available" ]; then
                    log_warning "    Interface is available. Attempting to delete..."
                    if aws ec2 delete-network-interface --network-interface-id "${eni_id}"; then
                        log_success "    Successfully deleted network interface ${eni_id}"
                    else
                        log_error "    Failed to delete network interface ${eni_id}"
                        has_non_vpc_endpoint=true
                    fi
                else
                    log_warning "    Interface is in use but not a VPC endpoint. Please check the associated service."
                    has_non_vpc_endpoint=true
                fi
            fi
        done <<< "${eni_ids}"
        
        # Only return failure if we found non-VPC endpoint dependencies
        if [ "${has_non_vpc_endpoint}" = "true" ]; then
            return 1
        fi
    fi
    
    return 0
}

# Function to delete a security group
delete_security_group() {
    local sg_id="$1"
    local sg_name="$2"
    local max_attempts="$3"
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        log_warning "Deleting security group: ${sg_name} (Attempt ${attempt}/${max_attempts})"
        
        # Check for dependencies first
        if ! check_security_group_dependencies "${sg_id}" "${sg_name}"; then
            log_warning "Security group ${sg_name} has dependencies. Waiting for them to be removed..."
            sleep 30
            attempt=$((attempt + 1))
            continue
        fi
        
        if aws ec2 delete-security-group --group-id "${sg_id}"; then
            log_success "Successfully deleted security group: ${sg_name}"
            return 0
        fi
        
        # Check if the group still exists
        if ! aws ec2 describe-security-groups --group-ids "${sg_id}" >/dev/null 2>&1; then
            log_success "Security group ${sg_name} no longer exists"
            return 0
        fi
        
        log_warning "Security group deletion failed, retrying..."
        sleep 10
        attempt=$((attempt + 1))
    done
    
    log_error "Failed to delete security group ${sg_name} after ${max_attempts} attempts"
    return 1
}

# Function to process security group rules
process_security_group_rules() {
    local sg_id="$1"
    local rules="$2"
    
    while IFS=$'\t' read -r rule_id is_egress; do
        delete_security_group_rule "${sg_id}" "${rule_id}" "${is_egress}" 3
    done <<< "${rules}"
    
    # Wait for rules to be removed
    sleep 5
}

# Step 1: Remove Web ACL associations first
log_warning "Removing Web ACL associations..."
WEB_ACL_ARNS=$(aws wafv2 list-web-acls \
    --scope REGIONAL \
    --region "${AWS_REGION}" \
    --query "WebACLs[?Name=='${SERVICE_NAME}-waf'].ARN" \
    --output text)

if [ -n "${WEB_ACL_ARNS}" ]; then
    while read -r WEB_ACL_ARN; do
        if [ -n "${WEB_ACL_ARN}" ]; then
            log_warning "Found Web ACL: ${WEB_ACL_ARN}"
            RESOURCES=$(aws wafv2 list-resources-for-web-acl \
                --web-acl-arn "${WEB_ACL_ARN}" \
                --resource-type APP_RUNNER \
                --region "${AWS_REGION}" \
                --output text)
            
            while read -r RESOURCE_ARN; do
                if [ -n "${RESOURCE_ARN}" ]; then
                    log_warning "Disassociating from resource: ${RESOURCE_ARN}"
                    aws wafv2 disassociate-web-acl \
                        --resource-arn "${RESOURCE_ARN}" \
                        --region "${AWS_REGION}"
                fi
            done <<< "${RESOURCES}"
        fi
    done <<< "${WEB_ACL_ARNS}"
fi

# Step 2: Remove the Web ACL itself
log_warning "Removing Web ACL..."
WEB_ACL_ID=$(aws wafv2 list-web-acls \
    --scope REGIONAL \
    --region "${AWS_REGION}" \
    --query "WebACLs[?Name=='${SERVICE_NAME}-waf'].Id" \
    --output text)

if [ -n "${WEB_ACL_ID}" ] && [ "${WEB_ACL_ID}" != "None" ]; then
    log_warning "Found Web ACL ID: ${WEB_ACL_ID}, getting lock token..."
    LOCK_TOKEN=$(aws wafv2 get-web-acl \
        --name "${SERVICE_NAME}-waf" \
        --scope REGIONAL \
        --region "${AWS_REGION}" \
        --id "${WEB_ACL_ID}" \
        --query 'LockToken' \
        --output text)
    
    if [ -n "${LOCK_TOKEN}" ] && [ "${LOCK_TOKEN}" != "None" ]; then
        log_warning "Deleting Web ACL..."
        aws wafv2 delete-web-acl \
            --name "${SERVICE_NAME}-waf" \
            --scope REGIONAL \
            --region "${AWS_REGION}" \
            --id "${WEB_ACL_ID}" \
            --lock-token "${LOCK_TOKEN}"
        
        log_success "Web ACL deleted successfully"
    fi
fi

# Clean up security group rules
log_warning "Cleaning up security group rules..."

# Find all security groups associated with our service
SECURITY_GROUPS=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=${SERVICE_NAME}-*" \
    --query 'SecurityGroups[*].[GroupId,GroupName]' \
    --output text)

if [ -n "${SECURITY_GROUPS}" ] && [ "${SECURITY_GROUPS}" != "None" ]; then
    while IFS=$'\t' read -r sg_id sg_name; do
        if [[ "${sg_name}" == *"${DEPLOY_MODE}"* ]]; then
            log_warning "Processing security group: ${sg_name} (${sg_id})"
            
            # Get all security group rules
            RULES=$(aws ec2 describe-security-group-rules \
                --filters "Name=group-id,Values=${sg_id}" \
                --query 'SecurityGroupRules[*].[SecurityGroupRuleId,IsEgress]' \
                --output text)
            
            if [ -n "${RULES}" ] && [ "${RULES}" != "None" ]; then
                process_security_group_rules "${sg_id}" "${RULES}"
            fi
            
            # Try to delete the security group
            delete_security_group "${sg_id}" "${sg_name}" 10
        fi
    done <<< "${SECURITY_GROUPS}"
else
    log_warning "No security groups found matching pattern: ${SERVICE_NAME}-*"
fi

log_success "Security cleanup completed" 