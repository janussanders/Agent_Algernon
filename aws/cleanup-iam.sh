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

# Set region explicitly
AWS_REGION="us-west-2"
export AWS_REGION

# Function to wait for role deletion
wait_for_role_deletion() {
    local role_name="$1"
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if ! aws iam get-role --role-name "${role_name}" >/dev/null 2>&1; then
            log_success "Role ${role_name} deleted successfully"
            return 0
        fi
        log_warning "Waiting for role ${role_name} deletion... (Attempt ${attempt}/${max_attempts})"
        sleep 10
        attempt=$((attempt + 1))
    done
    
    log_error "Timeout waiting for role deletion"
    return 1
}

# Function to clean up policy versions
cleanup_policy_versions() {
    local policy_arn="$1"
    
    # List all policy versions
    local versions=$(aws iam list-policy-versions \
        --policy-arn "${policy_arn}" \
        --query 'Versions[?!IsDefaultVersion].VersionId' \
        --output text)
    
    if [ -n "${versions}" ]; then
        log_warning "Cleaning up policy versions for ${policy_arn}"
        for version in ${versions}; do
            log_warning "Deleting policy version: ${version}"
            aws iam delete-policy-version \
                --policy-arn "${policy_arn}" \
                --version-id "${version}" || true
        done
    fi
}

# Function to clean up role
cleanup_role() {
    local role_name="$1"
    
    log_warning "Cleaning up role: ${role_name}"
    
    # List and detach managed policies
    local managed_policies=$(aws iam list-attached-role-policies \
        --role-name "${role_name}" \
        --query 'AttachedPolicies[*].PolicyArn' \
        --output text)
    
    if [ -n "${managed_policies}" ]; then
        for policy_arn in ${managed_policies}; do
            log_warning "Detaching managed policy: ${policy_arn}"
            aws iam detach-role-policy \
                --role-name "${role_name}" \
                --policy-arn "${policy_arn}" || true
        done
    fi
    
    # List and delete inline policies
    local inline_policies=$(aws iam list-role-policies \
        --role-name "${role_name}" \
        --query 'PolicyNames[*]' \
        --output text)
    
    if [ -n "${inline_policies}" ]; then
        for policy_name in ${inline_policies}; do
            log_warning "Deleting inline policy: ${policy_name}"
            aws iam delete-role-policy \
                --role-name "${role_name}" \
                --policy-name "${policy_name}" || true
        done
    fi
    
    # Delete instance profile associations
    local instance_profiles=$(aws iam list-instance-profiles-for-role \
        --role-name "${role_name}" \
        --query 'InstanceProfiles[*].InstanceProfileName' \
        --output text)
    
    if [ -n "${instance_profiles}" ]; then
        for profile_name in ${instance_profiles}; do
            log_warning "Removing role from instance profile: ${profile_name}"
            aws iam remove-role-from-instance-profile \
                --instance-profile-name "${profile_name}" \
                --role-name "${role_name}" || true
            
            # Delete the instance profile itself
            log_warning "Deleting instance profile: ${profile_name}"
            aws iam delete-instance-profile \
                --instance-profile-name "${profile_name}" || true
        done
    fi
    
    # Wait for detachments to complete
    sleep 10
    
    # Delete the role
    log_warning "Deleting role: ${role_name}"
    if aws iam delete-role --role-name "${role_name}"; then
        wait_for_role_deletion "${role_name}"
    else
        log_error "Failed to delete role: ${role_name}"
    fi
}

# Main cleanup process
log_warning "Starting IAM cleanup for ${DEPLOY_MODE} environment..."

# Clean up WebSocket API policy if it exists
POLICY_NAME="rag-app-websocket-policy"
POLICY_ARN=$(aws iam list-policies \
    --scope Local \
    --query "Policies[?PolicyName=='${POLICY_NAME}'].Arn" \
    --output text)

if [ -n "${POLICY_ARN}" ] && [ "${POLICY_ARN}" != "None" ]; then
    log_warning "Found WebSocket API policy: ${POLICY_ARN}"
    cleanup_policy_versions "${POLICY_ARN}"
    aws iam delete-policy --policy-arn "${POLICY_ARN}" || true
fi

# Find and cleanup IAM roles
log_warning "Finding IAM roles to clean up..."
ROLE_NAMES=$(aws iam list-roles \
    --query "Roles[?contains(RoleName, 'algernon-${DEPLOY_MODE}')].RoleName" \
    --output text)

if [ -n "${ROLE_NAMES}" ] && [ "${ROLE_NAMES}" != "None" ]; then
    for ROLE_NAME in ${ROLE_NAMES}; do
        cleanup_role "${ROLE_NAME}"
    done
else
    log_warning "No matching IAM roles found for ${DEPLOY_MODE} mode"
fi

log_success "IAM cleanup completed" 