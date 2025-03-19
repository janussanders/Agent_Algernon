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

# Image tags
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
IMAGE_TAG="${TIMESTAMP}"
LATEST_TAG="latest"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting deployment process...${NC}"

# Step 1: Configure AWS CLI
echo -e "${YELLOW}Configuring AWS CLI...${NC}"
aws configure set region ${AWS_REGION}

# Step 2: Login to ECR
echo -e "${YELLOW}Logging into ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Step 3: Build and tag Docker images
echo -e "${YELLOW}Building Docker images...${NC}"
docker-compose -f docker/docker-compose.prod.yml build

# Tag images
echo -e "${YELLOW}Tagging images...${NC}"
docker tag ${ECR_REPOSITORY}:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}
docker tag ${ECR_REPOSITORY}:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${LATEST_TAG}

# Step 4: Push images to ECR
echo -e "${YELLOW}Pushing images to ECR...${NC}"
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${LATEST_TAG}

# Step 5: Update ECS task definition
echo -e "${YELLOW}Updating ECS task definition...${NC}"
TASK_DEFINITION=$(aws ecs describe-task-definition --task-definition ${ECS_TASK_DEFINITION} --region ${AWS_REGION})
NEW_TASK_DEFINITION=$(echo $TASK_DEFINITION | jq --arg IMAGE "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}" '.taskDefinition | .containerDefinitions[0].image = $IMAGE | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)')

# Register new task definition
TASK_DEFINITION_ARN=$(aws ecs register-task-definition --region ${AWS_REGION} --cli-input-json "$NEW_TASK_DEFINITION" | jq -r .taskDefinition.taskDefinitionArn)

# Step 6: Update ECS service
echo -e "${YELLOW}Updating ECS service...${NC}"
aws ecs update-service --cluster ${ECS_CLUSTER} --service ${ECS_SERVICE} --task-definition ${TASK_DEFINITION_ARN} --region ${AWS_REGION}

# Step 7: Wait for deployment to complete
echo -e "${YELLOW}Waiting for deployment to complete...${NC}"
aws ecs wait services-stable --cluster ${ECS_CLUSTER} --services ${ECS_SERVICE} --region ${AWS_REGION}

echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}New image: ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}${NC}" 