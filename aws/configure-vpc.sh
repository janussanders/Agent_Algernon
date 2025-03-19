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

log_warning "Configuring VPC infrastructure for ${DEPLOY_MODE} environment"

# Verify AWS credentials
log_warning "Verifying AWS credentials..."
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "AWS credentials are invalid or not properly configured"
    exit 1
fi

# Clean up existing resources
log_warning "Cleaning up existing resources..."
aws ec2 describe-nat-gateways --filter "Name=state,Values=failed" --query "NatGateways[*].NatGatewayId" --output text | while read -r nat_id; do
    if [ ! -z "$nat_id" ]; then
        log_warning "Deleting failed NAT Gateway: ${nat_id}"
        aws ec2 delete-nat-gateway --nat-gateway-id "${nat_id}"
        sleep 10
    fi
done

# Get list of unused Elastic IPs
UNUSED_EIPS=$(aws ec2 describe-addresses --query "Addresses[?AssociationId==null].AllocationId" --output text)
if [ ! -z "$UNUSED_EIPS" ]; then
    log_warning "Found unused Elastic IPs, cleaning up..."
    for eip_id in $UNUSED_EIPS; do
        log_warning "Releasing Elastic IP: ${eip_id}"
        aws ec2 release-address --allocation-id "${eip_id}"
    done
fi

# Create VPC
log_warning "Creating VPC..."
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block 10.0.0.0/16 \
    --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-vpc}]" \
    --query "Vpc.VpcId" \
    --output text)

if [ -z "${VPC_ID}" ]; then
    log_error "Failed to create VPC"
    exit 1
fi

log_success "Created VPC with ID: ${VPC_ID}"

# Enable DNS hostnames and DNS support
aws ec2 modify-vpc-attribute \
    --vpc-id "${VPC_ID}" \
    --enable-dns-hostnames

aws ec2 modify-vpc-attribute \
    --vpc-id "${VPC_ID}" \
    --enable-dns-support

# Create Internet Gateway
log_warning "Creating Internet Gateway..."
IGW_ID=$(aws ec2 create-internet-gateway \
    --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-igw}]" \
    --query "InternetGateway.InternetGatewayId" \
    --output text)

if [ -z "${IGW_ID}" ]; then
    log_error "Failed to create Internet Gateway"
    exit 1
fi

log_success "Created Internet Gateway with ID: ${IGW_ID}"

# Attach Internet Gateway to VPC
log_warning "Attaching Internet Gateway to VPC..."
aws ec2 attach-internet-gateway \
    --internet-gateway-id "${IGW_ID}" \
    --vpc-id "${VPC_ID}"

# Create public subnets
log_warning "Creating public subnet in us-west-2a..."
PUBLIC_SUBNET_1=$(aws ec2 create-subnet \
    --vpc-id "${VPC_ID}" \
    --availability-zone us-west-2a \
    --cidr-block 10.0.1.0/24 \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-public-subnet-0}]" \
    --query "Subnet.SubnetId" \
    --output text)

if [ -z "${PUBLIC_SUBNET_1}" ]; then
    log_error "Failed to create public subnet in us-west-2a"
    exit 1
fi

log_success "Created public subnet ${PUBLIC_SUBNET_1} in us-west-2a"

log_warning "Creating public subnet in us-west-2b..."
PUBLIC_SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id "${VPC_ID}" \
    --availability-zone us-west-2b \
    --cidr-block 10.0.2.0/24 \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-public-subnet-1}]" \
    --query "Subnet.SubnetId" \
    --output text)

if [ -z "${PUBLIC_SUBNET_2}" ]; then
    log_error "Failed to create public subnet in us-west-2b"
    exit 1
fi

log_success "Created public subnet ${PUBLIC_SUBNET_2} in us-west-2b"

# Create private subnets
log_warning "Creating private subnet in us-west-2a..."
PRIVATE_SUBNET_1=$(aws ec2 create-subnet \
    --vpc-id "${VPC_ID}" \
    --availability-zone us-west-2a \
    --cidr-block 10.0.10.0/24 \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-private-subnet-0}]" \
    --query "Subnet.SubnetId" \
    --output text)

if [ -z "${PRIVATE_SUBNET_1}" ]; then
    log_error "Failed to create private subnet in us-west-2a"
    exit 1
fi

log_success "Created private subnet ${PRIVATE_SUBNET_1} in us-west-2a"

log_warning "Creating private subnet in us-west-2b..."
PRIVATE_SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id "${VPC_ID}" \
    --availability-zone us-west-2b \
    --cidr-block 10.0.11.0/24 \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-private-subnet-1}]" \
    --query "Subnet.SubnetId" \
    --output text)

if [ -z "${PRIVATE_SUBNET_2}" ]; then
    log_error "Failed to create private subnet in us-west-2b"
    exit 1
fi

log_success "Created private subnet ${PRIVATE_SUBNET_2} in us-west-2b"

# Export private subnet IDs for App Runner
export SUBNET_IDS="${PRIVATE_SUBNET_1},${PRIVATE_SUBNET_2}"
log_success "Created private subnets for App Runner: ${SUBNET_IDS}"

# Wait for subnets to be fully propagated
log_warning "Waiting for subnets to be fully propagated..."
for subnet_id in ${PRIVATE_SUBNET_1} ${PRIVATE_SUBNET_2}; do
    MAX_RETRIES=10
    RETRY_COUNT=0
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        SUBNET_STATE=$(aws ec2 describe-subnets \
            --subnet-ids "${subnet_id}" \
            --query "Subnets[0].State" \
            --output text)
        
        if [ "${SUBNET_STATE}" == "available" ]; then
            AVAILABLE_IPS=$(aws ec2 describe-subnets \
                --subnet-ids "${subnet_id}" \
                --query "Subnets[0].AvailableIpAddressCount" \
                --output text)
            
            CIDR=$(aws ec2 describe-subnets \
                --subnet-ids "${subnet_id}" \
                --query "Subnets[0].CidrBlock" \
                --output text)
            
            log_success "Subnet ${subnet_id} details:"
            log_success "  State: ${SUBNET_STATE}"
            log_success "  Available IPs: ${AVAILABLE_IPS}"
            log_success "  CIDR: ${CIDR}"
            log_success "  (Attempt $((RETRY_COUNT + 1))/${MAX_RETRIES})"
            break
        fi
        
        log_warning "Subnet ${subnet_id} is not available yet, waiting... (Attempt $((RETRY_COUNT + 1))/${MAX_RETRIES})"
        sleep 5
        RETRY_COUNT=$((RETRY_COUNT + 1))
    done
    
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        log_error "Timeout waiting for subnet ${subnet_id} to be available"
        exit 1
    fi
done

# Create route table
log_warning "Creating route table..."
ROUTE_TABLE_ID=$(aws ec2 create-route-table \
    --vpc-id "${VPC_ID}" \
    --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-rt}]" \
    --query "RouteTable.RouteTableId" \
    --output text)

if [ -z "${ROUTE_TABLE_ID}" ]; then
    log_error "Failed to create route table"
    exit 1
fi

# Create route to Internet Gateway
log_warning "Creating route to Internet Gateway..."
aws ec2 create-route \
    --route-table-id "${ROUTE_TABLE_ID}" \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id "${IGW_ID}"

# Associate subnets with route table
log_warning "Associating subnets with route table..."
for subnet_id in ${PUBLIC_SUBNET_1} ${PUBLIC_SUBNET_2}; do
    aws ec2 associate-route-table \
        --route-table-id "${ROUTE_TABLE_ID}" \
        --subnet-id "${subnet_id}"
done

# Create security group
log_warning "Creating security group for microservices..."
SECURITY_GROUP_ID=$(aws ec2 create-security-group \
    --group-name "algernon-${DEPLOY_MODE}-sg" \
    --description "Security group for Algernon microservices" \
    --vpc-id "${VPC_ID}" \
    --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-sg}]" \
    --query "GroupId" \
    --output text)

if [ -z "${SECURITY_GROUP_ID}" ]; then
    log_error "Failed to create security group"
    exit 1
fi

export SECURITY_GROUP_ID

# Create NAT Gateway
log_warning "Creating NAT Gateway..."
# First, allocate an Elastic IP
EIP_ALLOCATION_ID=$(aws ec2 allocate-address \
    --domain vpc \
    --query "AllocationId" \
    --output text)

if [ -z "${EIP_ALLOCATION_ID}" ]; then
    log_error "Failed to allocate Elastic IP"
    exit 1
fi

# Create NAT Gateway in the first public subnet
NAT_GATEWAY_ID=$(aws ec2 create-nat-gateway \
    --subnet-id "${PUBLIC_SUBNET_1}" \
    --allocation-id "${EIP_ALLOCATION_ID}" \
    --tag-specifications "ResourceType=natgateway,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-nat}]" \
    --query "NatGateway.NatGatewayId" \
    --output text)

if [ -z "${NAT_GATEWAY_ID}" ]; then
    log_error "Failed to create NAT Gateway"
    exit 1
fi

# Wait for NAT Gateway to be available
log_warning "Waiting for NAT Gateway to be available..."
aws ec2 wait nat-gateway-available --nat-gateway-ids "${NAT_GATEWAY_ID}"

# Create private route table
log_warning "Creating private route table..."
PRIVATE_ROUTE_TABLE_ID=$(aws ec2 create-route-table \
    --vpc-id "${VPC_ID}" \
    --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-private-rt}]" \
    --query "RouteTable.RouteTableId" \
    --output text)

if [ -z "${PRIVATE_ROUTE_TABLE_ID}" ]; then
    log_error "Failed to create private route table"
    exit 1
fi

# Add route to NAT Gateway
aws ec2 create-route \
    --route-table-id "${PRIVATE_ROUTE_TABLE_ID}" \
    --destination-cidr-block 0.0.0.0/0 \
    --nat-gateway-id "${NAT_GATEWAY_ID}"

# Associate private subnets with private route table
for subnet_id in ${PRIVATE_SUBNET_1} ${PRIVATE_SUBNET_2}; do
    aws ec2 associate-route-table \
        --route-table-id "${PRIVATE_ROUTE_TABLE_ID}" \
        --subnet-id "${subnet_id}"
done

# Configure security group rules
log_warning "Configuring security group rules..."

# Allow SSH access
aws ec2 authorize-security-group-ingress \
    --group-id "${SECURITY_GROUP_ID}" \
    --ip-permissions '[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH access"}]}]'

# Allow internal Qdrant access from within VPC
aws ec2 authorize-security-group-ingress \
    --group-id "${SECURITY_GROUP_ID}" \
    --ip-permissions '[{
        "IpProtocol": "tcp",
        "FromPort": 6333,
        "ToPort": 6334,
        "IpRanges": [{"CidrIp": "10.0.0.0/8", "Description": "Allow internal Qdrant access"}]
    }]'

# Allow Streamlit web UI access
aws ec2 authorize-security-group-ingress \
    --group-id "${SECURITY_GROUP_ID}" \
    --ip-permissions '[{
        "IpProtocol": "tcp",
        "FromPort": 8501,
        "ToPort": 8501,
        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Allow Streamlit web UI access"}]
    }]'

# Allow HTTP/HTTPS access
aws ec2 authorize-security-group-ingress \
    --group-id "${SECURITY_GROUP_ID}" \
    --ip-permissions '[{
        "IpProtocol": "tcp",
        "FromPort": 80,
        "ToPort": 80,
        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Allow HTTP access"}]
    }]'

aws ec2 authorize-security-group-ingress \
    --group-id "${SECURITY_GROUP_ID}" \
    --ip-permissions '[{
        "IpProtocol": "tcp",
        "FromPort": 443,
        "ToPort": 443,
        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Allow HTTPS access"}]
    }]'

# Allow all outbound traffic
aws ec2 authorize-security-group-egress \
    --group-id "${SECURITY_GROUP_ID}" \
    --ip-permissions '[{
        "IpProtocol": "-1",
        "FromPort": -1,
        "ToPort": -1,
        "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Allow all outbound traffic"}]
    }]' 2>/dev/null || true

# Check if default egress rule exists
log_warning "Checking existing egress rules..."
EXISTING_EGRESS=$(aws ec2 describe-security-groups \
    --group-ids "${SECURITY_GROUP_ID}" \
    --query "SecurityGroups[0].IpPermissionsEgress[*].IpProtocol" \
    --output text)

if [ -z "${EXISTING_EGRESS}" ]; then
    aws ec2 authorize-security-group-egress \
        --group-id "${SECURITY_GROUP_ID}" \
        --ip-permissions '[{"IpProtocol": "-1", "FromPort": -1, "ToPort": -1, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]'
    log_success "Added default egress rule"
else
    log_success "Default egress rule already exists"
fi

# Create VPC endpoints
log_warning "Creating VPC endpoints..."

# Create ECR API endpoint
log_warning "Creating ecr-api endpoint..."
ECR_API_ENDPOINT=$(aws ec2 create-vpc-endpoint \
    --vpc-id "${VPC_ID}" \
    --vpc-endpoint-type Interface \
    --service-name "com.amazonaws.${AWS_REGION}.ecr.api" \
    --subnet-ids "${PRIVATE_SUBNET_1}" "${PRIVATE_SUBNET_2}" \
    --security-group-ids "${SECURITY_GROUP_ID}" \
    --tag-specifications "ResourceType=vpc-endpoint,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-ecr-api}]" \
    --query "VpcEndpoint.VpcEndpointId" \
    --output text)

if [ -z "${ECR_API_ENDPOINT}" ]; then
    log_error "Failed to create ECR API endpoint"
    exit 1
fi

# Wait for ECR API endpoint to be available
log_warning "Waiting for VPC endpoint ${ECR_API_ENDPOINT} to become available..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    STATE=$(aws ec2 describe-vpc-endpoints --vpc-endpoint-ids "${ECR_API_ENDPOINT}" --query "VpcEndpoints[0].State" --output text)
    if [ "$STATE" == "available" ]; then
        break
    fi
    log_warning "VPC endpoint ${ECR_API_ENDPOINT} state: ${STATE} (Attempt $((RETRY_COUNT + 1))/${MAX_RETRIES})"
    sleep 10
    RETRY_COUNT=$((RETRY_COUNT + 1))
done
log_success "Successfully created and verified ecr-api endpoint (${ECR_API_ENDPOINT})"

# Create ECR DKR endpoint
log_warning "Creating ecr-dkr endpoint..."
ECR_DKR_ENDPOINT=$(aws ec2 create-vpc-endpoint \
    --vpc-id "${VPC_ID}" \
    --vpc-endpoint-type Interface \
    --service-name "com.amazonaws.${AWS_REGION}.ecr.dkr" \
    --subnet-ids "${PRIVATE_SUBNET_1}" "${PRIVATE_SUBNET_2}" \
    --security-group-ids "${SECURITY_GROUP_ID}" \
    --tag-specifications "ResourceType=vpc-endpoint,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-ecr-dkr}]" \
    --query "VpcEndpoint.VpcEndpointId" \
    --output text)

if [ -z "${ECR_DKR_ENDPOINT}" ]; then
    log_error "Failed to create ECR DKR endpoint"
    exit 1
fi

# Wait for ECR DKR endpoint to be available
log_warning "Waiting for VPC endpoint ${ECR_DKR_ENDPOINT} to become available..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    STATE=$(aws ec2 describe-vpc-endpoints --vpc-endpoint-ids "${ECR_DKR_ENDPOINT}" --query "VpcEndpoints[0].State" --output text)
    if [ "$STATE" == "available" ]; then
        break
    fi
    log_warning "VPC endpoint ${ECR_DKR_ENDPOINT} state: ${STATE} (Attempt $((RETRY_COUNT + 1))/${MAX_RETRIES})"
    sleep 10
    RETRY_COUNT=$((RETRY_COUNT + 1))
done
log_success "Successfully created and verified ecr-dkr endpoint (${ECR_DKR_ENDPOINT})"

# Create CloudWatch Logs endpoint
log_warning "Creating logs endpoint..."
LOGS_ENDPOINT=$(aws ec2 create-vpc-endpoint \
    --vpc-id "${VPC_ID}" \
    --vpc-endpoint-type Interface \
    --service-name "com.amazonaws.${AWS_REGION}.logs" \
    --subnet-ids "${PRIVATE_SUBNET_1}" "${PRIVATE_SUBNET_2}" \
    --security-group-ids "${SECURITY_GROUP_ID}" \
    --tag-specifications "ResourceType=vpc-endpoint,Tags=[{Key=Name,Value=algernon-${DEPLOY_MODE}-logs}]" \
    --query "VpcEndpoint.VpcEndpointId" \
    --output text)

if [ -z "${LOGS_ENDPOINT}" ]; then
    log_error "Failed to create CloudWatch Logs endpoint"
    exit 1
fi

# Wait for CloudWatch Logs endpoint to be available
log_warning "Waiting for VPC endpoint ${LOGS_ENDPOINT} to become available..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    STATE=$(aws ec2 describe-vpc-endpoints --vpc-endpoint-ids "${LOGS_ENDPOINT}" --query "VpcEndpoints[0].State" --output text)
    if [ "$STATE" == "available" ]; then
        break
    fi
    log_warning "VPC endpoint ${LOGS_ENDPOINT} state: ${STATE} (Attempt $((RETRY_COUNT + 1))/${MAX_RETRIES})"
    sleep 10
    RETRY_COUNT=$((RETRY_COUNT + 1))
done
log_success "Successfully created and verified logs endpoint (${LOGS_ENDPOINT})"

# Function to wait for VPC connector to be ready
wait_for_vpc_connector() {
    local connector_arn="$1"
    local max_attempts=30
    local attempt=1
    
    log_warning "Waiting for VPC Connector ${connector_arn} to become active..."
    
    while [ $attempt -le $max_attempts ]; do
        # Get connector status using text output
        local status=$(aws apprunner describe-vpc-connector \
            --vpc-connector-arn "${connector_arn}" \
            --query 'VpcConnector.Status' \
            --output text 2>/dev/null)
        
        if [ $? -ne 0 ]; then
            log_error "Failed to get VPC Connector status"
            return 1
        fi
        
        # Get additional details for troubleshooting
        local details=$(aws apprunner describe-vpc-connector \
            --vpc-connector-arn "${connector_arn}" \
            --query 'VpcConnector.{Subnets:Subnets,SecurityGroups:SecurityGroups,Error:Error}' \
            --output table 2>/dev/null)
        
        log_warning "VPC Connector status: ${status} (Attempt ${attempt}/${max_attempts})"
        if [ ! -z "${details}" ]; then
            log_warning "Details:"
            echo "${details}"
        fi
        
        case "${status}" in
            "ACTIVE")
                log_success "VPC Connector is ready"
                return 0
                ;;
            "FAILED")
                log_error "VPC Connector creation failed"
                return 1
                ;;
            "PENDING"|"IN_PROGRESS")
                log_warning "VPC Connector is still being created..."
                ;;
            *)
                log_error "VPC Connector in unexpected state: ${status}"
                return 1
                ;;
        esac
        
        sleep 10
        attempt=$((attempt + 1))
    done
    
    log_error "Timeout waiting for VPC Connector to become active"
    return 1
}

# Function to check existing VPC connectors
check_existing_vpc_connectors() {
    local next_token=""
    local max_attempts=10
    local attempt=1
    
    log_warning "Checking for existing VPC connectors..."
    
    while [ $attempt -le $max_attempts ]; do
        local response
        if [ -z "${next_token}" ]; then
            response=$(aws apprunner list-vpc-connectors \
                --query 'VpcConnectors[].{Name:VpcConnectorName,Status:Status,Subnets:Subnets}' \
                --output table 2>/dev/null)
        else
            response=$(aws apprunner list-vpc-connectors \
                --next-token "${next_token}" \
                --query 'VpcConnectors[].{Name:VpcConnectorName,Status:Status,Subnets:Subnets}' \
                --output table 2>/dev/null)
        fi
        
        if [ $? -ne 0 ]; then
            log_warning "Failed to get VPC connector list (Attempt ${attempt}/${max_attempts})"
            sleep 10
            attempt=$((attempt + 1))
            continue
        fi
        
        if [ ! -z "${response}" ]; then
            log_warning "Existing VPC connectors:"
            echo "${response}"
        fi
        
        # Get next token if available
        next_token=$(aws apprunner list-vpc-connectors \
            --query 'NextToken' \
            --output text 2>/dev/null)
        
        if [ -z "${next_token}" ]; then
            break
        fi
        
        attempt=$((attempt + 1))
    done
}

# Create App Runner VPC Connector
log_warning "Creating App Runner VPC Connector..."
VPC_CONNECTOR_NAME="algernon-${DEPLOY_MODE}-vpc-connector"

# Check existing VPC connectors first
check_existing_vpc_connectors

# Log the subnet and security group details before creation
log_warning "VPC Connector creation details:"
log_warning "  Name: ${VPC_CONNECTOR_NAME}"
log_warning "  Subnets: ${SUBNET_IDS}"
log_warning "  Security Group: ${SECURITY_GROUP_ID}"

# Verify subnet and security group details before creation
log_warning "Verifying subnet and security group details..."
for subnet_id in ${PRIVATE_SUBNET_1} ${PRIVATE_SUBNET_2}; do
    # Get full subnet details in JSON format
    subnet_json=$(aws ec2 describe-subnets \
        --subnet-ids "${subnet_id}" \
        --output json)
    
    if [ $? -ne 0 ]; then
        log_error "Failed to get subnet details for ${subnet_id}"
        exit 1
    fi
    
    # Log all subnet details for debugging
    log_warning "Full subnet details for ${subnet_id}:"
    echo "${subnet_json}" | jq '.'
    
    # Verify subnet is in the correct VPC
    subnet_vpc_id=$(echo "${subnet_json}" | jq -r '.Subnets[0].VpcId')
    
    if [ "${subnet_vpc_id}" != "${VPC_ID}" ]; then
        log_error "Subnet ${subnet_id} is not in the correct VPC"
        exit 1
    fi
    
    # Additional subnet checks
    subnet_state=$(echo "${subnet_json}" | jq -r '.Subnets[0].State')
    subnet_available=$(echo "${subnet_json}" | jq -r '.Subnets[0].AvailableIpAddressCount')
    subnet_cidr=$(echo "${subnet_json}" | jq -r '.Subnets[0].CidrBlock')
    subnet_az=$(echo "${subnet_json}" | jq -r '.Subnets[0].AvailabilityZone')
    
    log_warning "Subnet ${subnet_id} verification:"
    log_warning "  State: ${subnet_state}"
    log_warning "  Available IPs: ${subnet_available}"
    log_warning "  CIDR: ${subnet_cidr}"
    log_warning "  AZ: ${subnet_az}"
    log_warning "  VPC: ${subnet_vpc_id}"
done

# Create the VPC connector with text output
VPC_CONNECTOR_ARN=$(aws apprunner create-vpc-connector \
    --vpc-connector-name "${VPC_CONNECTOR_NAME}" \
    --subnets "${PRIVATE_SUBNET_1}" "${PRIVATE_SUBNET_2}" \
    --security-groups "${SECURITY_GROUP_ID}" \
    --query 'VpcConnector.VpcConnectorArn' \
    --output text 2>&1)

if [ $? -ne 0 ]; then
    log_error "Failed to create VPC Connector"
    log_error "Error: ${VPC_CONNECTOR_ARN}"
    exit 1
fi

if [ -z "${VPC_CONNECTOR_ARN}" ] || [ "${VPC_CONNECTOR_ARN}" = "None" ]; then
    log_error "Failed to get VPC Connector ARN"
    exit 1
fi

# Wait for the VPC connector to be ready
if ! wait_for_vpc_connector "${VPC_CONNECTOR_ARN}"; then
    log_error "VPC Connector failed to become active"
    exit 1
fi

# Export VPC Connector ARN
export VPC_CONNECTOR_ARN

# Update vpc_config.sh with all the VPC details
cat > "${SCRIPT_DIR}/vpc_config.sh" << EOF
#!/bin/bash
# VPC Configuration - Generated on $(date +"%Y-%m-%d %H:%M:%S")
# Environment: ${DEPLOY_MODE}
# Region: ${AWS_REGION}

export VPC_ID="${VPC_ID}"
export SUBNET_IDS="${SUBNET_IDS}"
export SECURITY_GROUP_ID="${SECURITY_GROUP_ID}"
export VPC_CONNECTOR_ARN="${VPC_CONNECTOR_ARN}"

# VPC Endpoints
EOF

# Add VPC endpoint information
aws ec2 describe-vpc-endpoints \
    --filters "Name=vpc-id,Values=${VPC_ID}" \
    --query 'VpcEndpoints[].{ID:VpcEndpointId,Service:ServiceName}' \
    --output json | jq -r '.[] | "# " + .Service + ": " + .ID' >> "${SCRIPT_DIR}/vpc_config.sh"

log_success "VPC configuration completed successfully"