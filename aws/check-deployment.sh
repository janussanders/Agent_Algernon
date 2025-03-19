#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Helper functions
log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_warning() { echo -e "${YELLOW}! $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}" >&2; }

# Source configuration
source "$(dirname "$0")/config.sh"
source "$(dirname "$0")/utils.sh"

# Get App Runner service details
SERVICE_ARN=$(aws apprunner list-services \
    --query "ServiceSummaryList[?contains(ServiceName, '${SERVICE_NAME}')].ServiceArn" \
    --output text)

if [ -z "$SERVICE_ARN" ]; then
    log_error "No App Runner service found"
    exit 1
fi

# Check service configuration
echo "App Runner Service Configuration:"
aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --query 'Service.{
        CPU: InstanceConfiguration.Cpu,
        Memory: InstanceConfiguration.Memory,
        Port: SourceConfiguration.ImageRepository.ImageConfiguration.Port,
        StartCommand: SourceConfiguration.ImageRepository.ImageConfiguration.StartCommand,
        Status: Status,
        URL: ServiceUrl
    }' \
    --output table

echo -e "\nService Events:"
aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --query 'Service.ServiceEvents[0:5].[Time,Message]' \
    --output table

# Check container logs
echo -e "\nChecking container logs..."
LOG_GROUP="/aws/apprunner/${SERVICE_NAME}"

if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" >/dev/null 2>&1; then
    LATEST_STREAM=$(aws logs describe-log-streams \
        --log-group-name "$LOG_GROUP" \
        --order-by LastEventTime \
        --descending \
        --limit 1 \
        --query 'logStreams[0].logStreamName' \
        --output text)
    
    if [ -n "$LATEST_STREAM" ]; then
        aws logs get-log-events \
            --log-group-name "$LOG_GROUP" \
            --log-stream-name "$LATEST_STREAM" \
            --limit 20 \
            --query 'events[*].[timestamp,message]' \
            --output table
    else
        log_warning "No log streams found"
    fi
else
    log_warning "No log streams found"
fi

# Check for common issues
echo -e "\nChecking for common issues..."

# Get detailed service configuration
aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --query 'Service.{
        AutoScaling: AutoScalingConfigurationSummary,
        HealthCheck: HealthCheckConfiguration,
        Network: NetworkConfiguration
    }' \
    --output table

# Check ECR image
IMAGE_URI=$(aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --query 'Service.SourceConfiguration.ImageRepository.ImageIdentifier' \
    --output text)

if [ -n "$IMAGE_URI" ]; then
    echo -e "\nChecking ECR image:"
    REPO_NAME=$(echo "$IMAGE_URI" | cut -d'/' -f2 | cut -d':' -f1)
    TAG=$(echo "$IMAGE_URI" | cut -d':' -f2)
    
    if aws ecr describe-images --repository-name "$REPO_NAME" --image-ids imageTag="$TAG" >/dev/null 2>&1; then
        log_success "Image $IMAGE_URI exists in ECR"
    else
        log_error "Image $IMAGE_URI not found in ECR"
    fi
fi

# Check IAM roles
check_iam_roles

# Check for common issues
echo -e "\nChecking for common issues..."

# Get detailed service configuration
aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --query 'Service.{
        AutoScaling: AutoScalingConfigurationSummary,
        HealthCheck: HealthCheckConfiguration,
        Network: NetworkConfiguration
    }' \
    --output table

# Check ECR image
IMAGE_URI=$(aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --query 'Service.SourceConfiguration.ImageRepository.ImageIdentifier' \
    --output text)

if [ -n "$IMAGE_URI" ]; then
    echo -e "\nChecking ECR image:"
    REPO_NAME=$(echo "$IMAGE_URI" | cut -d'/' -f2 | cut -d':' -f1)
    TAG=$(echo "$IMAGE_URI" | cut -d':' -f2)
    
    if aws ecr describe-images --repository-name "$REPO_NAME" --image-ids imageTag="$TAG" >/dev/null 2>&1; then
        log_success "Image $IMAGE_URI exists in ECR"
    else
        log_error "Image $IMAGE_URI not found in ECR"
    fi
fi

# Check IAM roles
echo -e "\nChecking IAM roles:"
for role in "$ECR_ACCESS_ROLE" "$SERVICE_ROLE"; do
    if aws iam get-role --role-name "$role" >/dev/null 2>&1; then
        log_success "Role $role exists"
    else
        log_error "Role $role not found"
    fi
done 