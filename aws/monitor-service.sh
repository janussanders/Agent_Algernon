#!/bin/bash

# Source configuration
source "$(dirname "$0")/utils.sh"
source "$(dirname "$0")/config.sh"

# Check if deployment mode is provided
if [ -z "$1" ]; then
    echo "Error: Deployment mode not provided"
    echo "Usage: $0 <dev|prod|update>"
    exit 1
fi

DEPLOY_MODE="$1"
SERVICE_NAME="algernon-${DEPLOY_MODE}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Helper functions
log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_warning() { echo -e "${YELLOW}! $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}" >&2; }

# Get service ARN
SERVICE_ARN=$(aws apprunner list-services \
    --region "${AWS_REGION}" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
    --output text)

if [ -z "$SERVICE_ARN" ]; then
    log_error "Could not find App Runner service '${SERVICE_NAME}'"
    exit 1
fi

echo "Monitoring App Runner service status..."
while true; do
    # Get service status
    STATUS=$(aws apprunner describe-service \
        --region "${AWS_REGION}" \
        --service-arn "$SERVICE_ARN" \
        --query 'Service.Status' \
        --output text)
    
    # Get service URL
    URL=$(aws apprunner describe-service \
        --region "${AWS_REGION}" \
        --service-arn "$SERVICE_ARN" \
        --query 'Service.ServiceUrl' \
        --output text)
    
    # Clear line and show status
    printf "\rService Status: "
    case "$STATUS" in
        "RUNNING")
            log_success "RUNNING - https://${URL}"
            ;;
        "OPERATION_IN_PROGRESS")
            log_warning "DEPLOYING..."
            ;;
        *)
            log_error "$STATUS"
            ;;
    esac
    
    # Exit if service is running
    if [ "$STATUS" = "RUNNING" ]; then
        echo -e "\nService is ready! Opening in default browser..."
        # Open in browser (works on macOS, Linux with xdg-open, or Windows with start)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            open "https://${URL}"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            xdg-open "https://${URL}"
        elif [[ "$OSTYPE" == "msys" ]]; then
            start "https://${URL}"
        fi
        break
    fi
    
    sleep 5
done 