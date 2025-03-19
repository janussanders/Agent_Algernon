#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/utils.sh"
source "${SCRIPT_DIR}/config.sh"

# Function to get the latest service ARN
get_service_arn() {
    local service_name="algernon-${DEPLOY_MODE}"
    aws apprunner list-services \
        --query "ServiceSummaryList[?ServiceName=='${service_name}'].ServiceArn" \
        --output text
}

# Function to get service configuration
get_service_config() {
    local service_arn="$1"
    log_warning "Fetching App Runner service configuration..."
    aws apprunner describe-service --service-arn "${service_arn}" | jq '.'
}

# Function to get environment variables
get_environment_vars() {
    local service_arn="$1"
    log_warning "Fetching App Runner environment variables..."
    aws apprunner describe-service \
        --service-arn "${service_arn}" \
        --query "Service.InstanceConfiguration.InstanceRoleArn" \
        --output text

    aws apprunner describe-service \
        --service-arn "${service_arn}" \
        --query "Service.SourceConfiguration.ImageRepository.ImageConfiguration.RuntimeEnvironmentVariables" \
        --output json | jq '.'
}

# Function to get deployment logs
get_deployment_logs() {
    local service_arn="$1"
    log_warning "Fetching deployment logs..."
    
    # Get all operations and sort them by timestamp
    local operations=$(aws apprunner list-operations \
        --service-arn "${service_arn}" \
        --query 'OperationSummaryList[*]' \
        --output json)
    
    if [ -n "${operations}" ] && [ "${operations}" != "[]" ]; then
        # Get the most recent operation
        echo "${operations}" | jq 'sort_by(.StartedAt) | reverse | .[0]'
        
        # Show recent operations summary
        log_warning "Recent operations summary:"
        echo "${operations}" | jq 'sort_by(.StartedAt) | reverse | .[0:5] | .[] | {Type, Status, StartedAt, EndedAt}'
    else
        log_error "No deployment operations found"
    fi
}

# Function to check if CloudWatch logging is enabled
check_cloudwatch_logging() {
    local service_arn="$1"
    log_warning "Checking CloudWatch logging configuration..."
    
    # Check if observability configuration exists
    local observability_config=$(aws apprunner describe-service \
        --service-arn "${service_arn}" \
        --query "Service.ObservabilityConfiguration" \
        --output json)
    
    if [ "${observability_config}" = "null" ] || [ -z "${observability_config}" ]; then
        log_warning "CloudWatch logging is not enabled for this service."
        log_warning "To enable CloudWatch logging:"
        log_warning "1. Create an observability configuration:"
        log_warning "   aws apprunner create-observability-configuration \\"
        log_warning "       --observability-configuration-name \"${SERVICE_NAME}-${DEPLOY_MODE}-logs\" \\"
        log_warning "       --trace-configuration Vendor=AWSXRAY"
        log_warning ""
        log_warning "2. Update the service to use the configuration:"
        log_warning "   aws apprunner update-service \\"
        log_warning "       --service-arn \"${service_arn}\" \\"
        log_warning "       --observability-configuration \\"
        log_warning "       ObservabilityEnabled=true,ObservabilityConfigurationArn=<config-arn>"
        return 1
    fi
    return 0
}

# Function to get CloudWatch logs
get_cloudwatch_logs() {
    local service_arn="$1"
    local minutes=${2:-60}  # Default to last 60 minutes
    log_warning "Fetching CloudWatch logs for the last ${minutes} minutes..."
    
    # First check if CloudWatch logging is enabled
    if ! check_cloudwatch_logging "${service_arn}"; then
        return 1
    fi
    
    # Extract service name from ARN
    local service_name=$(echo "${service_arn}" | cut -d'/' -f2)
    local log_group="/aws/apprunner/${service_name}"
    
    # Check if log group exists
    if ! aws logs describe-log-groups --log-group-name-prefix "${log_group}" --query 'logGroups[0].logGroupName' --output text &>/dev/null; then
        log_warning "Log group ${log_group} does not exist yet. This could mean:"
        log_warning "1. The service is newly created and hasn't started logging yet"
        log_warning "2. The service hasn't generated any logs"
        log_warning "3. The IAM role doesn't have permissions to write logs"
        log_warning ""
        log_warning "Available App Runner log groups:"
        aws logs describe-log-groups \
            --log-group-name-prefix "/aws/apprunner" \
            --query 'logGroups[*].[logGroupName,storedBytes]' \
            --output table
        
        # Check IAM role permissions
        local instance_role=$(aws apprunner describe-service \
            --service-arn "${service_arn}" \
            --query "Service.InstanceConfiguration.InstanceRoleArn" \
            --output text)
        
        if [ -n "${instance_role}" ]; then
            log_warning "Checking IAM role permissions..."
            aws iam get-role --role-name "${instance_role#*/}" \
                --query 'Role.AssumeRolePolicyDocument' \
                --output json || true
            
            aws iam list-role-policies --role-name "${instance_role#*/}" || true
            aws iam list-attached-role-policies --role-name "${instance_role#*/}" || true
        fi
        return 0
    fi
    
    # Get log streams sorted by last event time
    local streams=$(aws logs describe-log-streams \
        --log-group-name "${log_group}" \
        --order-by LastEventTime \
        --descending \
        --max-items 5 \
        --query 'logStreams[*].logStreamName' \
        --output text)
    
    if [ -z "${streams}" ]; then
        log_warning "No log streams found in ${log_group}"
        return 0
    fi
    
    # Calculate start time in milliseconds
    local start_time=$(($(date +%s) - minutes * 60))000
    
    for stream in ${streams}; do
        log_warning "Logs from stream: ${stream}"
        aws logs get-log-events \
            --log-group-name "${log_group}" \
            --log-stream-name "${stream}" \
            --start-time "${start_time}" \
            --query 'events[*].message' \
            --output text | grep -v '^$' || true
        echo "----------------------------------------"
    done
}

# Function to get container health checks
get_health_checks() {
    local service_arn="$1"
    log_warning "Fetching health check status..."
    aws apprunner describe-service \
        --service-arn "${service_arn}" \
        --query "Service.HealthCheckConfiguration" \
        --output json | jq '.'
}

# Main execution
main() {
    local service_arn=$(get_service_arn)
    if [ -z "${service_arn}" ]; then
        log_error "No App Runner service found for ${DEPLOY_MODE} mode"
        exit 1
    fi
    
    log_success "Found service ARN: ${service_arn}"
    echo "============================================"
    
    # Get service configuration
    log_warning "Service Configuration:"
    get_service_config "${service_arn}"
    echo "============================================"
    
    # Get environment variables
    log_warning "Environment Variables:"
    get_environment_vars "${service_arn}"
    echo "============================================"
    
    # Get deployment logs
    log_warning "Deployment Logs:"
    get_deployment_logs "${service_arn}"
    echo "============================================"
    
    # Get health check status
    log_warning "Health Check Status:"
    get_health_checks "${service_arn}"
    echo "============================================"
    
    # Get CloudWatch logs (last hour by default)
    get_cloudwatch_logs "${service_arn}"
}

# Check if deployment mode is provided
if [ -z "$1" ]; then
    log_error "Deployment mode not provided"
    log_warning "Usage: $0 <dev|prod>"
    exit 1
fi

DEPLOY_MODE="$1"
export DEPLOY_MODE

# Execute main function
main 