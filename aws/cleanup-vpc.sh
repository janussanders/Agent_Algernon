#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# Function to wait for VPC Connector deletion with better status handling
wait_for_vpc_connector_deletion() {
    local connector_arn="$1"
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        # First check if the connector exists at all
        if ! aws apprunner describe-vpc-connector --vpc-connector-arn "${connector_arn}" >/dev/null 2>&1; then
            log_success "VPC Connector ${connector_arn} deleted successfully"
            return 0
        fi
        
        local status=$(aws apprunner describe-vpc-connector \
            --vpc-connector-arn "${connector_arn}" \
            --query 'VpcConnector.Status' \
            --output text 2>/dev/null || echo "DELETED")
        
        # Get additional details for troubleshooting
        local details=$(aws apprunner describe-vpc-connector \
            --vpc-connector-arn "${connector_arn}" \
            --query 'VpcConnector.{Subnets:Subnets,SecurityGroups:SecurityGroups}' \
            --output table 2>/dev/null)
        
        log_warning "VPC Connector ${connector_arn} status: ${status} (Attempt ${attempt}/${max_attempts})"
        if [ ! -z "${details}" ]; then
            log_warning "Details:"
            echo "${details}"
        fi
        
        case "${status}" in
            "DELETED"|"DELETE_FAILED"|"INACTIVE")
                if [ "${status}" = "INACTIVE" ]; then
                    sleep 5
                fi
                return 0
                ;;
            *)
                sleep 10
                ;;
        esac
        
        attempt=$((attempt + 1))
    done
    
    log_error "Timeout waiting for VPC Connector deletion"
    return 1
}

# Function to cleanup VPC dependencies
cleanup_vpc_dependencies() {
    local vpc_id="$1"
    
    # Check if this is a default VPC
    local is_default=$(aws ec2 describe-vpcs \
        --vpc-ids "${vpc_id}" \
        --query 'Vpcs[0].IsDefault' \
        --output text)
    
    if [ "${is_default}" = "true" ]; then
        log_warning "Skipping default VPC: ${vpc_id}"
        return 0
    fi
    
    log_warning "Cleaning up dependencies for VPC: ${vpc_id}"
    
    # Clean up VPC Endpoints with pagination
    log_warning "Cleaning up VPC Endpoints..."
    local endpoints_response
    local next_token=""
    declare -a endpoint_ids=()
    
    while true; do
        # Build the command with proper token handling
        if [ -z "${next_token}" ]; then
            endpoints_response=$(aws ec2 describe-vpc-endpoints \
                --filters "Name=vpc-id,Values=${vpc_id}" \
                --max-items 100 \
                --output json)
        else
            endpoints_response=$(aws ec2 describe-vpc-endpoints \
                --filters "Name=vpc-id,Values=${vpc_id}" \
                --max-items 100 \
                --starting-token "${next_token}" \
                --output json)
        fi
        
        # Process current page
        while IFS= read -r endpoint_id; do
            if [ -n "${endpoint_id}" ]; then
                endpoint_ids+=("${endpoint_id}")
            fi
        done < <(echo "${endpoints_response}" | jq -r '.VpcEndpoints[].VpcEndpointId')
        
        # Get next token
        next_token=$(echo "${endpoints_response}" | jq -r '.NextToken')
        if [ -z "${next_token}" ] || [ "${next_token}" = "null" ]; then
            break
        fi
    done
    
    # Delete endpoints and wait for each one to be fully deleted
    if [ ${#endpoint_ids[@]} -gt 0 ]; then
        for endpoint_id in "${endpoint_ids[@]}"; do
            log_warning "Deleting VPC Endpoint: ${endpoint_id}"
            
            # Get the network interfaces associated with this endpoint
            local endpoint_enis=$(aws ec2 describe-vpc-endpoints \
                --vpc-endpoint-ids "${endpoint_id}" \
                --query 'VpcEndpoints[0].NetworkInterfaceIds' \
                --output text)
            
            # Delete the endpoint
            aws ec2 delete-vpc-endpoints --vpc-endpoint-ids "${endpoint_id}"
            
            # Wait for endpoint deletion and its network interfaces to be cleaned up
            local max_attempts=30
            local attempt=1
            while [ $attempt -le $max_attempts ]; do
                if ! aws ec2 describe-vpc-endpoints \
                    --vpc-endpoint-ids "${endpoint_id}" >/dev/null 2>&1; then
                    # Endpoint is deleted, now wait for ENIs to be cleaned up
                    local all_enis_gone=true
                    for eni in ${endpoint_enis}; do
                        if aws ec2 describe-network-interfaces --network-interface-ids "${eni}" >/dev/null 2>&1; then
                            all_enis_gone=false
                            break
                        fi
                    done
                    if [ "${all_enis_gone}" = "true" ]; then
                        log_success "VPC Endpoint ${endpoint_id} and its network interfaces deleted successfully"
                        break
                    fi
                fi
                log_warning "Waiting for endpoint ${endpoint_id} and its network interfaces to be deleted... (Attempt ${attempt}/${max_attempts})"
                sleep 20
                attempt=$((attempt + 1))
            done
            if [ $attempt -gt $max_attempts ]; then
                log_error "Timeout waiting for endpoint ${endpoint_id} deletion"
            fi
        done
    fi
    
    # Clean up NAT Gateways
    log_warning "Cleaning up NAT Gateways..."
    local nat_gateways=$(aws ec2 describe-nat-gateways \
        --filter "Name=vpc-id,Values=${vpc_id}" \
        --query 'NatGateways[*].NatGatewayId' \
        --output text)
    
    if [ -n "${nat_gateways}" ]; then
        for nat_id in ${nat_gateways}; do
            log_warning "Deleting NAT Gateway: ${nat_id}"
            aws ec2 delete-nat-gateway --nat-gateway-id "${nat_id}"
        done
        
        # Wait for NAT Gateways to be deleted
        log_warning "Waiting for NAT Gateways to be deleted..."
        local max_attempts=30
        local attempt=1
        while [ $attempt -le $max_attempts ]; do
            local all_deleted=true
            for nat_id in ${nat_gateways}; do
                local status=$(aws ec2 describe-nat-gateways \
                    --nat-gateway-ids "${nat_id}" \
                    --query 'NatGateways[0].State' \
                    --output text 2>/dev/null || echo "deleted")
                if [ "${status}" != "deleted" ]; then
                    all_deleted=false
                    break
                fi
            done
            if [ "${all_deleted}" = "true" ]; then
                log_success "All NAT Gateways deleted successfully"
                break
            fi
            log_warning "Waiting for NAT Gateways to be deleted... (Attempt ${attempt}/${max_attempts})"
            sleep 20
            attempt=$((attempt + 1))
        done
    fi
    
    # Clean up Network Interfaces with improved handling
    log_warning "Cleaning up Network Interfaces..."
    local network_interfaces=$(aws ec2 describe-network-interfaces \
        --filters "Name=vpc-id,Values=${vpc_id}" \
        --query 'NetworkInterfaces[*].NetworkInterfaceId' \
        --output text)
    
    for eni_id in ${network_interfaces}; do
        # Get interface details
        local eni_details=$(aws ec2 describe-network-interfaces \
            --network-interface-ids "${eni_id}" \
            --output json)
        
        # Skip if the interface is still attached to a VPC endpoint (it will be cleaned up automatically)
        local interface_type=$(echo "${eni_details}" | jq -r '.NetworkInterfaces[0].InterfaceType')
        if [ "${interface_type}" = "vpc_endpoint" ]; then
            log_warning "Skipping VPC endpoint network interface ${eni_id}"
            continue
        fi
        
        # Get attachment ID if interface is attached
        local attachment_id=$(echo "${eni_details}" | jq -r '.NetworkInterfaces[0].Attachment.AttachmentId')
        
        if [ -n "${attachment_id}" ] && [ "${attachment_id}" != "null" ]; then
            log_warning "Force detaching network interface ${eni_id}"
            aws ec2 detach-network-interface \
                --attachment-id "${attachment_id}" \
                --force || true
            
            # Wait for detachment
            local max_attempts=15
            local attempt=1
            while [ $attempt -le $max_attempts ]; do
                local status=$(aws ec2 describe-network-interfaces \
                    --network-interface-ids "${eni_id}" \
                    --query 'NetworkInterfaces[0].Status' \
                    --output text)
                if [ "${status}" = "available" ]; then
                    break
                fi
                log_warning "Waiting for network interface ${eni_id} to detach... (Attempt ${attempt}/${max_attempts})"
                sleep 10
                attempt=$((attempt + 1))
            done
        fi
        
        # Delete with retries and proper status checking
        local delete_attempts=5
        local delete_attempt=1
        while [ $delete_attempt -le $delete_attempts ]; do
            if aws ec2 delete-network-interface --network-interface-id "${eni_id}" 2>/dev/null; then
                log_success "Successfully deleted network interface ${eni_id}"
                break
            fi
            
            # Check if the interface still exists
            if ! aws ec2 describe-network-interfaces --network-interface-ids "${eni_id}" >/dev/null 2>&1; then
                log_success "Network interface ${eni_id} no longer exists"
                break
            fi
            
            log_warning "Failed to delete network interface ${eni_id}, retrying... (Attempt ${delete_attempt}/${delete_attempts})"
            sleep 15
            delete_attempt=$((delete_attempt + 1))
        done
    done
    
    # Only handle orphaned security groups that might prevent VPC deletion
    # Main security group cleanup should be handled by cleanup-security.sh
    log_warning "Checking for orphaned security groups in VPC ${vpc_id}..."
    local security_groups=$(aws ec2 describe-security-groups \
        --filters "Name=vpc-id,Values=${vpc_id}" \
        --query "SecurityGroups[?GroupName!='default' && !starts_with(GroupName, '${SERVICE_NAME}')].GroupId" \
        --output text)
    
    if [ -n "${security_groups}" ] && [ "${security_groups}" != "None" ]; then
        log_warning "Found orphaned security groups to clean up"
        for sg_id in ${security_groups}; do
            log_warning "Attempting to delete orphaned security group: ${sg_id}"
            aws ec2 delete-security-group --group-id "${sg_id}" || true
        done
    fi
    
    # Clean up Internet Gateways
    log_warning "Cleaning up Internet Gateways..."
    local internet_gateways=$(aws ec2 describe-internet-gateways \
        --filters "Name=attachment.vpc-id,Values=${vpc_id}" \
        --query 'InternetGateways[*].InternetGatewayId' \
        --output text)
    
    for igw_id in ${internet_gateways}; do
        aws ec2 detach-internet-gateway --internet-gateway-id "${igw_id}" --vpc-id "${vpc_id}"
        aws ec2 delete-internet-gateway --internet-gateway-id "${igw_id}"
    done
    
    # Clean up Subnets
    log_warning "Cleaning up Subnets..."
    local subnets=$(aws ec2 describe-subnets \
        --filters "Name=vpc-id,Values=${vpc_id}" \
        --query 'Subnets[*].SubnetId' \
        --output text)
    
    for subnet_id in ${subnets}; do
        aws ec2 delete-subnet --subnet-id "${subnet_id}"
    done
    
    # Clean up Route Tables
    log_warning "Cleaning up Route Tables..."
    local route_tables=$(aws ec2 describe-route-tables \
        --filters "Name=vpc-id,Values=${vpc_id}" \
        --query 'RouteTables[?Associations[0].Main!=`true`].RouteTableId' \
        --output text)
    
    for rt_id in ${route_tables}; do
        aws ec2 delete-route-table --route-table-id "${rt_id}"
    done
    
    # Delete VPC
    log_warning "Deleting VPC: ${vpc_id}"
    aws ec2 delete-vpc --vpc-id "${vpc_id}"
}

# Main cleanup sequence
log_warning "Starting cleanup process..."

# Clean up VPC Connectors first
log_warning "Cleaning up VPC Connectors..."
RESPONSE=$(aws apprunner list-vpc-connectors --output json)
NEXT_TOKEN=$(echo "${RESPONSE}" | jq -r '.NextToken')

while true; do
    # Process current page of results
    echo "${RESPONSE}" | jq -c '.VpcConnectors[]' | while read -r connector; do
        name=$(echo "${connector}" | jq -r '.VpcConnectorName')
        arn=$(echo "${connector}" | jq -r '.VpcConnectorArn')
        status=$(echo "${connector}" | jq -r '.Status')
        
        # Check if this is one of our connectors
        if [[ "${name}" == *"algernon"* ]] || [[ "${name}" == *"${DEPLOY_MODE}"* ]]; then
            log_warning "Found VPC Connector to clean up: ${name} (${arn})"
            
            # Skip if connector is already being deleted
            if [ "${status}" = "PENDING_DELETION" ]; then
                log_warning "VPC Connector ${name} is already being deleted, waiting..."
                wait_for_vpc_connector_deletion "${arn}"
                continue
            fi
            
            # Check if the connector is in use
            services=$(aws apprunner list-services \
                --query "ServiceSummaryList[?VpcConnectorArn=='${arn}'].ServiceArn" \
                --output text)
            
            if [ -n "${services}" ] && [ "${services}" != "None" ]; then
                log_warning "VPC Connector ${name} is still in use by services, skipping..."
                continue
            fi
            
            log_warning "Deleting VPC Connector: ${name}"
            if aws apprunner delete-vpc-connector --vpc-connector-arn "${arn}"; then
                wait_for_vpc_connector_deletion "${arn}"
            else
                log_error "Failed to delete VPC Connector: ${name}"
            fi
        fi
    done
    
    # Check if there are more results to process
    if [ -z "${NEXT_TOKEN}" ] || [ "${NEXT_TOKEN}" = "null" ]; then
        break
    fi
    
    # Get next page of results using --next-token instead of --starting-token
    RESPONSE=$(aws apprunner list-vpc-connectors --next-token "${NEXT_TOKEN}" --output json)
    NEXT_TOKEN=$(echo "${RESPONSE}" | jq -r '.NextToken')
done

# Now proceed with VPC cleanup
log_warning "Finding Algernon VPCs in ${AWS_REGION}..."
VPC_IDS=$(aws ec2 describe-vpcs \
    --filters "Name=tag:Name,Values=${SERVICE_NAME}-${DEPLOY_MODE}-vpc" \
    --query 'Vpcs[*].VpcId' \
    --output text)

if [ -n "${VPC_IDS}" ] && [ "${VPC_IDS}" != "None" ]; then
    for VPC_ID in ${VPC_IDS}; do
        # Get VPC details including tags
        VPC_DETAILS=$(aws ec2 describe-vpcs --vpc-ids "${VPC_ID}")
        VPC_NAME=$(echo "${VPC_DETAILS}" | jq -r '.Vpcs[0].Tags[] | select(.Key=="Name") | .Value // "No Name"')
        IS_DEFAULT=$(echo "${VPC_DETAILS}" | jq -r '.Vpcs[0].IsDefault')
        
        if [ "${IS_DEFAULT}" = "true" ]; then
            log_warning "Skipping default VPC: ${VPC_ID}"
            continue
        fi
        
        log_warning "Processing Algernon VPC: ${VPC_ID} (${VPC_NAME})"
        cleanup_vpc_dependencies "${VPC_ID}"
    done
else
    log_warning "No Algernon VPCs found for ${DEPLOY_MODE} mode"
fi

# Reset VPC config file
log_warning "Cleaning up VPC configuration..."
cat > "${SCRIPT_DIR}/vpc_config.sh" << EOF
#!/bin/bash
export VPC_ID=""
export SUBNET_IDS=""
export SECURITY_GROUP_ID=""
export VPC_CONNECTOR_ARN=""
EOF

chmod +x "${SCRIPT_DIR}/vpc_config.sh"
log_success "VPC cleanup completed"