#!/bin/bash

# Exit on error
set -e

# Load environment variables
source .env

# AWS Configuration
AWS_REGION=${AWS_REGION:-"us-east-1"}
ECR_REPOSITORY=${ECR_REPOSITORY:-"rag-app"}
ECS_CLUSTER=${ECS_CLUSTER:-"rag-cluster"}
ECS_SERVICE=${ECS_SERVICE:-"rag-service"}
ECS_TASK_DEFINITION=${ECS_TASK_DEFINITION:-"rag-task"}

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Starting AWS resource setup...${NC}"

# Step 1: Create ECR Repository
echo -e "${YELLOW}Creating ECR repository...${NC}"
aws ecr create-repository \
    --repository-name ${ECR_REPOSITORY} \
    --region ${AWS_REGION} \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability MUTABLE || true

# Step 2: Create ECS Cluster
echo -e "${YELLOW}Creating ECS cluster...${NC}"
aws ecs create-cluster \
    --cluster-name ${ECS_CLUSTER} \
    --capacity-providers FARGATE \
    --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1 \
    --region ${AWS_REGION} || true

# Step 3: Create IAM Roles
echo -e "${YELLOW}Creating IAM roles...${NC}"

# Create ECS Task Execution Role
aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ecs-tasks.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }' || true

# Attach required policies to Task Execution Role
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy || true

# Create ECS Task Role
aws iam create-role \
    --role-name ecsTaskRole \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ecs-tasks.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }' || true

# Create and attach custom policy for Task Role
aws iam put-role-policy \
    --role-name ecsTaskRole \
    --policy-name ecsTaskPolicy \
    --policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ssm:GetParameters",
                    "ssm:GetParameter"
                ],
                "Resource": "arn:aws:ssm:*:*:parameter/rag-app/*"
            }
        ]
    }' || true

# Step 4: Create CloudWatch Log Group
echo -e "${YELLOW}Creating CloudWatch log group...${NC}"
aws logs create-log-group \
    --log-group-name /ecs/${ECS_TASK_DEFINITION} \
    --region ${AWS_REGION} || true

# Step 5: Create SSM Parameter for API Key
echo -e "${YELLOW}Creating SSM parameter for API key...${NC}"
aws ssm put-parameter \
    --name /rag-app/SAMBANOVA_API_KEY \
    --type SecureString \
    --value "${SAMBANOVA_API_KEY}" \
    --region ${AWS_REGION} || true

echo -e "${GREEN}AWS resource setup completed successfully!${NC}"
echo -e "${YELLOW}Please ensure the following resources are created:${NC}"
echo -e "1. ECR Repository: ${ECR_REPOSITORY}"
echo -e "2. ECS Cluster: ${ECS_CLUSTER}"
echo -e "3. IAM Roles: ecsTaskExecutionRole, ecsTaskRole"
echo -e "4. CloudWatch Log Group: /ecs/${ECS_TASK_DEFINITION}"
echo -e "5. SSM Parameter: /rag-app/SAMBANOVA_API_KEY" 