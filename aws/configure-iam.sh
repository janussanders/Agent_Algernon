#!/bin/bash

# Function to display usage
usage() {
    echo "Usage: $0 <dev|prod|update>"
    echo "  or   $0 (when called from deploy-stack.sh with DEPLOY_MODE set)"
}

# Check if DEPLOY_MODE is already set (from deploy-stack.sh)
if [ -z "${DEPLOY_MODE}" ]; then
    # If not set, check for command line argument
    if [ -z "$1" ]; then
        echo "Error: Deployment mode not provided"
        usage
        exit 1
    fi
    # Set DEPLOY_MODE from command line argument
    export DEPLOY_MODE="$1"
fi

# Validate deployment mode
case "${DEPLOY_MODE}" in
    dev|prod|update)
        echo "Setting up IAM roles for ${DEPLOY_MODE} environment"
        ;;
    *)
        echo "Error: Invalid deployment mode '${DEPLOY_MODE}'"
        usage
        exit 1
        ;;
esac

source "$(dirname "$0")/utils.sh"
source "$(dirname "$0")/config.sh"

# Debug deployment variables
log_warning "IAM Setup Configuration:"
log_warning "DEPLOY_MODE: ${DEPLOY_MODE}"
log_warning "ENVIRONMENT: ${ENVIRONMENT}"
log_warning "SERVICE_NAME: ${SERVICE_NAME}"
log_warning "ECR_ACCESS_ROLE: ${ECR_ACCESS_ROLE}"
log_warning "SERVICE_ROLE: ${SERVICE_ROLE}"

# Create the ECR Access Role
log_warning "Creating ECR Access role..."

# Trust policy for ECR Access Role
ECR_TRUST_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": [
                    "build.apprunner.amazonaws.com",
                    "apprunner.amazonaws.com"
                ]
            },
            "Action": [
                "sts:AssumeRole",
                "sts:TagSession"
            ]
        }
    ]
}'

# Create or update the ECR Access Role
if ! aws iam get-role --role-name "${ECR_ACCESS_ROLE}" 2>/dev/null; then
    log_warning "Creating ${ECR_ACCESS_ROLE}..."
    aws iam create-role \
        --role-name "${ECR_ACCESS_ROLE}" \
        --assume-role-policy-document "${ECR_TRUST_POLICY}" || {
            log_error "Failed to create ${ECR_ACCESS_ROLE}"
            exit 1
        }
    
    # Attach ECR policy
    aws iam attach-role-policy \
        --role-name "${ECR_ACCESS_ROLE}" \
        --policy-arn "${APPRUNNER_ECR_POLICY_ARN}" || {
            log_error "Failed to attach ECR policy to ${ECR_ACCESS_ROLE}"
            exit 1
        }
    
    log_success "Created ${ECR_ACCESS_ROLE}"
else
    # Update the trust relationship
    log_warning "Updating ${ECR_ACCESS_ROLE} trust relationship..."
    aws iam update-assume-role-policy \
        --role-name "${ECR_ACCESS_ROLE}" \
        --policy-document "${ECR_TRUST_POLICY}"
    log_success "Updated ${ECR_ACCESS_ROLE}"
fi

# Create the Service Role
log_warning "Creating Service role..."

# Trust policy for Service Role
SERVICE_TRUST_POLICY='{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {
            "Service": [
                "tasks.apprunner.amazonaws.com",
                "apprunner.amazonaws.com"
            ]
        },
        "Action": "sts:AssumeRole"
    }]
}'

# Create or update the Service Role
if ! aws iam get-role --role-name "${SERVICE_ROLE}" 2>/dev/null; then
    log_warning "Creating ${SERVICE_ROLE}..."
    aws iam create-role \
        --role-name "${SERVICE_ROLE}" \
        --assume-role-policy-document "${SERVICE_TRUST_POLICY}" || {
            log_error "Failed to create ${SERVICE_ROLE}"
            exit 1
        }
    
    # Attach required policies
    aws iam attach-role-policy \
        --role-name "${SERVICE_ROLE}" \
        --policy-arn "${APPRUNNER_INSTANCE_POLICY_ARN}" || {
            log_error "Failed to attach instance role policy"
            exit 1
        }
    
    log_success "Created ${SERVICE_ROLE}"
else
    # Update the trust relationship
    log_warning "Updating ${SERVICE_ROLE} trust relationship..."
    aws iam update-assume-role-policy \
        --role-name "${SERVICE_ROLE}" \
        --policy-document "${SERVICE_TRUST_POLICY}"
    log_success "Updated ${SERVICE_ROLE}"
fi

# Initial wait for role creation
log_warning "Waiting for initial role creation..."
sleep 15

# Function to wait for role to be available
wait_for_role() {
    local role_name="$1"
    local max_attempts=20
    local attempt=1
    
    log_warning "Waiting for role ${role_name} to be available..."
    
    while [ $attempt -le $max_attempts ]; do
        if aws iam get-role --role-name "${role_name}" >/dev/null 2>&1; then
            local role_arn=$(aws iam get-role \
                --role-name "${role_name}" \
                --query 'Role.Arn' \
                --output text)
            
            if [ -n "${role_arn}" ]; then
                log_success "Role ${role_name} is available"
                return 0
            fi
        fi
        
        log_warning "Role not fully available yet, waiting... (Attempt ${attempt}/${max_attempts})"
        sleep 6
        attempt=$((attempt + 1))
    done
    
    log_error "Timeout waiting for role ${role_name} to be available"
    return 1
}

# Verify roles are available
if ! wait_for_role "${SERVICE_ROLE}"; then
    log_error "Failed to verify ${SERVICE_ROLE}"
    exit 1
fi

if ! wait_for_role "${ECR_ACCESS_ROLE}"; then
    log_error "Failed to verify ${ECR_ACCESS_ROLE}"
    exit 1
fi

log_success "IAM roles setup completed"

# Create or update the App Runner service role
create_service_role() {
    local role_name="$1"
    local policy_arn="$2"
    
    # Create trust policy for App Runner
    local trust_policy='{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "tasks.apprunner.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }'
    
    # Create CloudWatch Logs policy
    local cloudwatch_policy='{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams"
                ],
                "Resource": [
                    "arn:aws:logs:*:*:log-group:/aws/apprunner/*",
                    "arn:aws:logs:*:*:log-group:/aws/apprunner/*:log-stream:*"
                ]
            }
        ]
    }'
    
    # Check if role exists
    if ! aws iam get-role --role-name "${role_name}" >/dev/null 2>&1; then
        log_warning "Creating IAM role: ${role_name}"
        aws iam create-role \
            --role-name "${role_name}" \
            --assume-role-policy-document "${trust_policy}" \
            --description "App Runner service role for ${SERVICE_NAME}" \
            > /dev/null
    fi
    
    # Attach the main policy
    aws iam attach-role-policy \
        --role-name "${role_name}" \
        --policy-arn "${policy_arn}"
    
    # Create and attach CloudWatch Logs policy
    local policy_name="${role_name}-cloudwatch-logs"
    if aws iam get-policy --policy-arn "arn:aws:iam::${AWS_ACCOUNT}:policy/${policy_name}" >/dev/null 2>&1; then
        aws iam delete-policy --policy-arn "arn:aws:iam::${AWS_ACCOUNT}:policy/${policy_name}"
    fi
    
    local policy_arn=$(aws iam create-policy \
        --policy-name "${policy_name}" \
        --policy-document "${cloudwatch_policy}" \
        --query 'Policy.Arn' \
        --output text)
    
    aws iam attach-role-policy \
        --role-name "${role_name}" \
        --policy-arn "${policy_arn}"
    
    log_success "IAM role ${role_name} configured with CloudWatch Logs permissions"
} 