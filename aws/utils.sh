#!/bin/bash

# Logging functions with colors but no labels
log_success() {
    echo -e "\033[0;32m$1\033[0m"
}

log_warning() {
    echo -e "\033[0;33m$1\033[0m"
}

log_error() {
    echo -e "\033[0;31m$1\033[0m" >&2
}

# Function to show a spinner
show_spinner() {
    local pid=$1
    local message="${2:-Working}"
    local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    
    # Clear line and show initial message
    printf "\r%s..." "$message"
    
    while kill -0 $pid 2>/dev/null; do
        # Read current status if available
        if [ -f /tmp/apprunner_status ]; then
            local status=$(cat /tmp/apprunner_status)
            printf "\r%s: %s" "$message" "$status"
        else
            # Show spinner if no status
            printf "\r%s... %s" "$message" "."
        fi
        sleep 0.1
    done
    
    # Clear spinner
    printf "\r"
}

# Function to check IAM roles
check_iam_roles() {
    echo -e "\nChecking IAM roles:"
    local failed=0
    for role in "$ECR_ACCESS_ROLE" "$SERVICE_ROLE"; do
        if aws iam get-role --role-name "$role" >/dev/null 2>&1; then
            log_success "Role $role exists"
        else
            log_error "Role $role not found"
            failed=1
        fi
    done
    return $failed
}

# Function to wait for service deletion
wait_for_service_deletion() {
    local service_name="$1"
    local max_attempts=30
    local attempt=1
    
    log_warning "Waiting for service ${service_name} to be fully deleted..."
    
    while [ $attempt -le $max_attempts ]; do
        if ! aws apprunner list-services \
            --region "${AWS_REGION}" \
            --query "ServiceSummaryList[?ServiceName=='${service_name}'].ServiceArn" \
            --output text | grep -q .; then
            log_success "Service ${service_name} is fully deleted"
            return 0
        fi
        log_warning "Service still exists, waiting... (attempt ${attempt}/${max_attempts})"
        sleep 10
        attempt=$((attempt + 1))
    done
    
    log_error "Timeout waiting for service deletion"
    return 1
}

# Function to fetch logs
fetch_logs() {
    local deploy_mode="$1"
    local context="$2"
    local max_retries=5
    local retry_count=0

    echo "Fetching logs (${context})..."
    
    # Get the service ARN
    local service_name="algernon-${deploy_mode}"
    local service_arn=$(aws apprunner list-services \
        --region "${AWS_REGION}" \
        --query "ServiceSummaryList[?ServiceName=='${service_name}'].ServiceArn" \
        --output text)
    
    if [ -z "${service_arn}" ]; then
        echo "! No service ARN found for ${service_name}"
        return 1
    fi
    
    # Get the log group name
    local log_group="/aws/apprunner/${service_name}/${service_arn##*/}/application"
    echo "! Checking for available log groups..."
    
    # Wait for log group to become available
    while [ ${retry_count} -lt ${max_retries} ]; do
        if aws logs describe-log-groups \
            --log-group-name-prefix "${log_group}" \
            --region "${AWS_REGION}" \
            --output text &>/dev/null; then
            break
        fi
        retry_count=$((retry_count + 1))
        if [ ${retry_count} -eq ${max_retries} ]; then
            echo "! Log group not found after ${max_retries} attempts"
            return 1
        fi
        sleep 2
    done
    
    # Get the most recent log stream
    local log_stream=$(aws logs describe-log-streams \
        --log-group-name "${log_group}" \
        --region "${AWS_REGION}" \
        --order-by LastEventTime \
        --descending \
        --max-items 1 \
        --query 'logStreams[0].logStreamName' \
        --output text)
    
    if [ -z "${log_stream}" ] || [ "${log_stream}" = "None" ]; then
        echo "! No log streams found"
        return 1
    fi
    
    # Get the most recent logs
    aws logs get-log-events \
        --log-group-name "${log_group}" \
        --log-stream-name "${log_stream}" \
        --region "${AWS_REGION}" \
        --limit 10 \
        --output table
    
    return 0
}

# Function to wait for service to be stable
wait_for_stable_state() {
    local service_arn="$1"
    local timeout=900  # 15 minutes timeout
    local start_time=$(date +%s)
    
    log_warning "Initializing service deployment..."
    log_warning "Service ARN: ${service_arn}"

    # Start monitoring in background
    (
        local last_status=""
        local last_operation=""

        while true; do
            local current_time=$(date +%s)
            local elapsed=$((current_time - start_time))
            
            if [ $elapsed -gt $timeout ]; then
                echo "Deployment timed out after $(($timeout / 60)) minutes" > /tmp/apprunner_status
                # Delete the service on timeout
                aws apprunner delete-service \
                    --region "${AWS_REGION}" \
                    --service-arn "${service_arn}" >/dev/null 2>&1
                exit 1
            fi

            # Get full service details
            local service_details
            service_details=$(aws apprunner describe-service \
                --region "${AWS_REGION}" \
                --service-arn "${service_arn}" 2>/dev/null)

            if [ $? -ne 0 ]; then
                echo "Checking App Runner service status..." > /tmp/apprunner_status
                sleep 5
                continue
            fi

            local status
            status=$(echo "${service_details}" | jq -r '.Service.Status')
            local operation_status
            operation_status=$(echo "${service_details}" | jq -r '.Service.OperationStatus // "UNKNOWN"')
            local error_message
            error_message=$(echo "${service_details}" | jq -r '.Service.ErrorMessage // empty')

            # Calculate elapsed time in minutes and seconds
            local elapsed_min=$((elapsed / 60))
            local elapsed_sec=$((elapsed % 60))
            
            # Format detailed status message
            local current_status="[${elapsed_min}m ${elapsed_sec}s] ${status}"
            if [ -n "${operation_status}" ] && [ "${operation_status}" != "UNKNOWN" ]; then
                current_status="${current_status} - ${operation_status}"
            fi

            if [ "$current_status" != "$last_status" ] || [ $((elapsed % 30)) -eq 0 ]; then
                case "${status}" in
                    "CREATING")
                        echo "${current_status} - Setting up App Runner infrastructure..." > /tmp/apprunner_status
                        ;;
                    "PROVISIONING")
                        echo "${current_status} - Provisioning containers..." > /tmp/apprunner_status
                        ;;
                    "OPERATION_IN_PROGRESS")
                        case "${operation_status}" in
                            "CREATING_RESOURCES")
                                echo "${current_status} - Creating AWS resources..." > /tmp/apprunner_status
                                ;;
                            "CONFIGURING_RESOURCES")
                                echo "${current_status} - Configuring service..." > /tmp/apprunner_status
                                ;;
                            "DEPLOYING")
                                echo "${current_status} - Deploying application..." > /tmp/apprunner_status
                                ;;
                            *)
                                echo "${current_status} ..." > /tmp/apprunner_status
                                ;;
                        esac
                        ;;
                    *)
                        echo "${current_status}" > /tmp/apprunner_status
                        ;;
                esac
                last_status="$current_status"
            fi

            case "${status}" in
                "RUNNING")
                    if [ "${operation_status}" = "FAILED" ]; then
                        echo "${current_status} - Operation failed: ${error_message}" > /tmp/apprunner_status
                        exit 1
                    fi
                    echo "${current_status} - Service is now running!" > /tmp/apprunner_status
                    exit 0
                    ;;
                "DELETED"|"DELETE_FAILED")
                    echo "${current_status} - Service was deleted or failed to delete" > /tmp/apprunner_status
                    exit 1
                    ;;
                "ERROR"|"OPERATION_FAILED"|"CREATE_FAILED"|"CONNECTION_FAILED")
                    echo "${current_status} - Service failed: ${error_message}" > /tmp/apprunner_status
                    exit 1
                    ;;
            esac

            sleep 5
        done
    ) &

    local monitor_pid=$!
    show_spinner $monitor_pid "Deploying service"
    wait $monitor_pid
    local result=$?

    # Clean up status file
    rm -f /tmp/apprunner_status

    if [ $result -eq 0 ]; then
        log_success "Service deployment completed successfully"
        fetch_logs "${DEPLOY_MODE}" "deployment completion"
        return 0
    else
        log_error "Service deployment failed"
        fetch_logs "${DEPLOY_MODE}" "deployment failure"
        # Delete the service if it still exists
        aws apprunner delete-service \
            --region "${AWS_REGION}" \
            --service-arn "${service_arn}" >/dev/null 2>&1
        return 1
    fi
}

# Function to wait for App Runner service to be ready
wait_for_service() {
    local service_arn="$1"
    local max_attempts=40
    local attempt=1
    local status

    while [ $attempt -le $max_attempts ]; do
        # Get status
        status=$(aws apprunner describe-service \
            --service-arn "${service_arn}" \
            --query 'Service.Status' \
            --output text)
        
        if [ -z "${status}" ] || [ "${status}" = "None" ]; then
            log_warning "Service ${service_arn} not found or status None (Attempt ${attempt}/${max_attempts})"
            sleep 10
            attempt=$((attempt + 1))
            continue
        fi
        
        log_warning "Service ${service_arn} status: ${status} (Attempt ${attempt}/${max_attempts})"
        
        if [ "${status}" = "RUNNING" ]; then
            log_success "Service is deployed and running"
            return 0
        elif [ "${status}" = "FAILED" ] || [ "${status}" = "CREATE_FAILED" ]; then
            log_error "Service failed to deploy"
            return 1
        fi
        
        sleep 20
        attempt=$((attempt + 1))
    done

    log_error "Timeout waiting for service to be ready"
    return 1
}

# Function to update config.sh with new values
update_config() {
    local key="$1"
    local value="$2"
    local config_file="${SCRIPT_DIR}/config.sh"
    
    # Check if key exists
    if grep -q "^export ${key}=" "${config_file}"; then
        # Update existing key
        sed -i.bak "s|^export ${key}=.*|export ${key}=\"${value}\"|" "${config_file}"
    else
        # Add new key
        echo "export ${key}=\"${value}\"" >> "${config_file}"
    fi
} 