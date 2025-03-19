#!/bin/bash

# Colors for output (if not already defined)
if [ -z "${GREEN}" ]; then
    export GREEN='\033[0;32m'
    export YELLOW='\033[1;33m'
    export RED='\033[0;31m'
    export NC='\033[0m'
fi

# Helper functions (if not already defined)
if [ -z "$(declare -f log_success)" ]; then
    log_success() { echo -e "${GREEN}✓ $1${NC}"; }
    log_warning() { echo -e "${YELLOW}! $1${NC}"; }
    log_error() { echo -e "${RED}✗ $1${NC}" >&2; }
fi

# AWS Configuration
# ----------------
# Central configuration file for AWS resources naming and settings

# Service name and environment
export SERVICE_NAME="algernon-prod"
export DEPLOY_MODE="prod"

# AWS Region and Account
export AWS_REGION="us-west-2"

# Get AWS Account ID if not already set
if [ -z "${AWS_ACCOUNT}" ]; then
    export AWS_ACCOUNT=$(aws sts get-caller-identity --query 'Account' --output text)
    if [ -z "${AWS_ACCOUNT}" ]; then
        log_error "Failed to get AWS account ID"
        exit 1
    fi
fi

# VPC Configuration
export VPC_CIDR="10.0.0.0/16"
export SUBNET_CIDRS=("10.0.1.0/24" "10.0.2.0/24")
export ZONES=("a" "b")

# Security Group and VPC Connector
VPC_CONFIG_FILE="$(dirname "$0")/vpc_config.sh"
if [ -f "${VPC_CONFIG_FILE}" ]; then
    source "${VPC_CONFIG_FILE}"
fi

# Service Configuration
export RAG_SERVICE_NAME="${SERVICE_NAME}-${DEPLOY_MODE}-rag"
export UI_SERVICE_NAME="${SERVICE_NAME}-${DEPLOY_MODE}-ui"

# Domain Configuration
export DOMAIN_NAME="example.com"
export SUBDOMAIN="${DEPLOY_MODE}.${DOMAIN_NAME}"

# ECR Repository names
export REPO_NAME="algernon"
export IMAGE_TAG="${DEPLOY_MODE}"

# Docker image tags
export RAG_IMAGE_TAG="latest"
export UI_IMAGE_TAG="latest"

# Set environment based on deployment mode
case "${DEPLOY_MODE}" in
    "dev")
        export ENVIRONMENT="development"
        ;;
    "prod")
        export ENVIRONMENT="production"
        ;;
    "update")
        export ENVIRONMENT="update"
        ;;
    *)
        echo "Error: Invalid DEPLOY_MODE '${DEPLOY_MODE}'"
        exit 1
        ;;
esac

# Set service name
SERVICE_NAME="algernon"  # Base name without environment

# IAM Role Names
export ECR_ACCESS_ROLE="algernon-ecr-access-role"
export SERVICE_ROLE="AppRunnerECSServiceRole"

# Construct the full ARNs
export ECR_ACCESS_ROLE_ARN="arn:aws:iam::688567306974:role/algernon-ecr-access-role"
export SERVICE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT}:role/${SERVICE_ROLE}"

# Set AWS managed policy ARNs (corrected policy names)
export APPRUNNER_ECR_POLICY_ARN="arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
export APPRUNNER_INSTANCE_POLICY_ARN="arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForInstanceAccess"

# Set repository names
export QDRANT_REPO_NAME="qdrant"

# Domain Configuration
export DOMAIN_NAME="www.janusinnovations.dev"
export BASE_PATH="/algernon"  # Path-based routing
export CUSTOM_DOMAIN="${DOMAIN_NAME}"  # Main domain, not subdomain

# Set ECR image URLs
export ECR_IMAGE="688567306974.dkr.ecr.us-west-2.amazonaws.com/algernon:rag-agent-prod"
export ECR_QDRANT_IMAGE="${ECR_IMAGE}"
export ECR_RAG_IMAGE="${ECR_IMAGE}"

# Port Configuration
export HTTP_PORT="8501"
export QDRANT_HTTP_PORT="6333"
export QDRANT_GRPC_PORT="6334"
export QDRANT_P2P_PORT="6335"

# App Runner Service URLs
# Note: These values are updated by configure-apprunner.sh
export QDRANT_HOST=""
export SERVICE_URL="2td2iu2vm7.us-west-2.awsapprunner.com2td2iu2vm7.us-west-2.awsapprunner.com"
export WEBSOCKET_API_URL=""

# SambaNova Configuration
export SAMBANOVA_API_KEY="b00e1d2e-492b-40ca-b2a8-dee9dc0913a9"

# Prevent AWS CLI pagination
export AWS_PAGER=""

# Validate environment is set
if [ -z "${ENVIRONMENT}" ]; then
    log_error "ENVIRONMENT not set. Please run this script through deploy-stack.sh"
    exit 1
fi

# Health Check Configuration
export HEALTH_CHECK_PATH="/health"
export HEALTH_CHECK_PORT="${QDRANT_HTTP_PORT}"
export HEALTH_CHECK_INTERVAL="20"
export HEALTH_CHECK_TIMEOUT="5"
export HEALTH_CHECK_HEALTHY_THRESHOLD="2"
export HEALTH_CHECK_UNHEALTHY_THRESHOLD="3"

# Add this function
update_vpc_config() {
    local config_file="${VPC_CONFIG_FILE}"
    echo "#!/bin/bash" > "${config_file}"
    [ -n "${VPC_ID}" ] && echo "export VPC_ID=${VPC_ID}" >> "${config_file}"
    [ -n "${SUBNET_IDS}" ] && echo "export SUBNET_IDS=\"${SUBNET_IDS// /,}\"" >> "${config_file}"
    [ -n "${SECURITY_GROUP_ID}" ] && echo "export SECURITY_GROUP_ID=${SECURITY_GROUP_ID}" >> "${config_file}"
    [ -n "${VPC_CONNECTOR_ARN}" ] && echo "export VPC_CONNECTOR_ARN=${VPC_CONNECTOR_ARN}" >> "${config_file}"
}

export APP_RUNNER_ARN="arn:aws:apprunner:us-west-2:688567306974:service/algernon-prod/f16399f2e48844c4a7fda5462fdc036c"
export PYTHONPATH="/app"
export PYTHONUNBUFFERED="1"
export DEBUG="false"
export PORT="6333"
export QDRANT_BIND_PORT="6333"
export QDRANT_PORT="6333"
export QDRANT_HTTPS="false"
export QDRANT_VERIFY_SSL="false"
export SAMBANOVA_URL=""
export STREAMLIT_DEBUG="false"
export STREAMLIT_SERVER_PORT="8501"
export STREAMLIT_SERVER_ADDRESS="0.0.0.0"
export STREAMLIT_SERVER_RUN_ON_SAVE="false"
export STREAMLIT_SERVER_ENABLE_CORS="true"
export STREAMLIT_SERVER_ENABLE_WEBSOCKET_COMPRESSION="true"
export STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION="false"
export STREAMLIT_SERVER_ENABLE_WEBSOCKET="true"
export STREAMLIT_SERVER_ENABLE_STATIC_SERVING="true"
export STREAMLIT_SERVER_MAX_MESSAGE_SIZE="200"
export STREAMLIT_CLIENT_SHOW_ERROR_DETAILS="false"
export STREAMLIT_CLIENT_TOOLBAR_MODE="minimal"
export STREAMLIT_BROWSER_GATHER_USAGE_STATS="false"
export STREAMLIT_THEME_BASE="light"
export QDRANT_SERVICE_URL="2td2iu2vm7.us-west-2.awsapprunner.com2td2iu2vm7.us-west-2.awsapprunner.com"
export QDRANT_HTTPS_URL="2td2iu2vm7.us-west-2.awsapprunner.com2td2iu2vm7.us-west-2.awsapprunner.com"
export QDRANT_WSS_URL="2td2iu2vm7.us-west-2.awsapprunner.com2td2iu2vm7.us-west-2.awsapprunner.com"
export ENVIRONMENT="production"
export VPC_CONNECTOR_ARN="arn:aws:apprunner:us-west-2:688567306974:vpcconnector\/algernon-prod-vpc-connector\/1\/3bf72f24b8044b47a7d74acd69b829c9"
export VPC_ID="vpc-03c7794fecbfbefda"
export SUBNET_IDS="subnet-0bb7848215c8e2457,subnet-09d221374fc72e550"
export SECURITY_GROUP_ID="sg-0f1d5a31415e055be"
export CONFIG_VERSION="20250315_163603"
export LAST_DEPLOY_TIMESTAMP="2025-03-16T02:36:03Z"
