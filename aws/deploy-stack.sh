#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source utilities first
source "${SCRIPT_DIR}/utils.sh"

# Check for AWS credentials
if [ ! -f "${HOME}/.aws/credentials" ]; then
    # Check for secure-config.sh
    if [ -f "${SCRIPT_DIR}/secure-config.sh" ]; then
        log_warning "Loading AWS credentials from secure-config.sh..."
        source "${SCRIPT_DIR}/secure-config.sh"
        
        # Ensure AWS credentials directory exists
        mkdir -p "${HOME}/.aws"
        
        # Create credentials file
        cat > "${HOME}/.aws/credentials" << EOF
[default]
aws_access_key_id=${AWS_ACCESS_KEY_ID}
aws_secret_access_key=${AWS_SECRET_ACCESS_KEY}
region=${AWS_REGION}
EOF
        chmod 600 "${HOME}/.aws/credentials"
        
        log_success "AWS credentials configured"
    else
        log_error "No AWS credentials found. Please either:"
        log_error "1. Configure AWS CLI using 'aws configure'"
        log_error "2. Create ${SCRIPT_DIR}/secure-config.sh with AWS credentials"
        exit 1
    fi
fi

# Verify AWS credentials work
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "AWS credentials are invalid or not properly configured"
    exit 1
fi

# Check if deployment mode is provided
if [ -z "$1" ]; then
    log_error "Deployment mode not provided"
    log_warning "Usage: $0 <dev|prod>"
    exit 1
fi

DEPLOY_MODE="$1"
export DEPLOY_MODE

# Initialize vpc_config.sh with empty values
cat > "${SCRIPT_DIR}/vpc_config.sh" << EOF
#!/bin/bash
export VPC_ID=""
export SUBNET_IDS=""
export SECURITY_GROUP_ID=""
export VPC_CONNECTOR_ARN=""
EOF

# Source configs after setting DEPLOY_MODE
source "${SCRIPT_DIR}/config.sh"
source "${SCRIPT_DIR}/vpc_config.sh"

# Add this function after the source statements
wait_for_resource_deletion() {
    local resource_type="$1"
    local check_command="$2"
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if ! eval "${check_command}"; then
            log_success "${resource_type} deleted successfully"
            return 0
        fi
        log_warning "Waiting for ${resource_type} deletion... (Attempt ${attempt}/${max_attempts})"
        sleep 10
        attempt=$((attempt + 1))
    done
    
    log_error "Timeout waiting for ${resource_type} deletion"
    return 1
}

# Cleanup Phase (in reverse dependency order)
log_warning "Starting cleanup phase..."

# 1. Clean up App Runner services (this includes domain configurations)
"${SCRIPT_DIR}/cleanup-apprunner.sh" "${DEPLOY_MODE}"
wait_for_resource_deletion "App Runner services" "aws apprunner list-services --query \"ServiceSummaryList[?contains(ServiceName, 'algernon')].ServiceArn\" --output text | grep -q ."

# 2. Clean up WebSocket API Gateway
"${SCRIPT_DIR}/cleanup-websocket.sh" "${DEPLOY_MODE}"

# 3. Clean up VPC resources first (this will clean up VPC endpoints)
"${SCRIPT_DIR}/cleanup-vpc.sh" "${DEPLOY_MODE}"

# 4. Clean up security resources (WAF and security groups)
log_warning "Cleaning up security resources..."
"${SCRIPT_DIR}/cleanup-security.sh" "${DEPLOY_MODE}"

# 5. Clean up IAM roles
"${SCRIPT_DIR}/cleanup-iam.sh" "${DEPLOY_MODE}"

# 6. Clean up CloudWatch logs
log_warning "Cleaning up CloudWatch logs..."
"${SCRIPT_DIR}/cleanup-logs.sh" "${DEPLOY_MODE}"

# 7. Clean up ECR (optional)
"${SCRIPT_DIR}/cleanup-ecr.sh" "${DEPLOY_MODE}"


# Deployment Phase (in dependency order)
log_warning "Starting deployment phase..."

# 1. Configure IAM (most fundamental)
log_warning "Configuring IAM roles..."
if ! "${SCRIPT_DIR}/configure-iam.sh" "${DEPLOY_MODE}"; then
    log_error "IAM configuration failed"
    exit 1
fi

# 2. Configure WebSocket API Gateway
log_warning "Configuring WebSocket API Gateway..."
if ! "${SCRIPT_DIR}/configure-websocket.sh" "${DEPLOY_MODE}"; then
    log_error "WebSocket API Gateway configuration failed"
    exit 1
fi

# 3. Configure VPC infrastructure (includes VPC, subnets, security groups, and endpoints)
log_warning "Configuring VPC infrastructure..."
if ! "${SCRIPT_DIR}/configure-vpc.sh" "${DEPLOY_MODE}"; then
    log_error "VPC configuration failed"
    exit 1
fi

# Re-source vpc_config to get new VPC values
source "${SCRIPT_DIR}/vpc_config.sh"
# Clean up any Mac OS X artifacts (optional)
"${SCRIPT_DIR}/../services/deepclean.sh"

# 4. Configure ECR and push images
log_warning "Configuring ECR repositories..."
if ! "${SCRIPT_DIR}/configure-ecr.sh" "${DEPLOY_MODE}"; then
    log_error "ECR configuration failed"
    exit 1
fi

# 5. Configure initial App Runner service
log_warning "Configuring initial App Runner service..."
if ! "${SCRIPT_DIR}/configure-apprunner.sh" "${DEPLOY_MODE}"; then
    log_error "App Runner configuration failed"
    exit 1
fi

# Deployment completed
log_success "Deployment completed successfully" 