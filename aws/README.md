# AWS Infrastructure

This directory contains AWS infrastructure configurations and deployment scripts for the RAG application.

## Directory Structure

```
aws/
├── ecs/                    # ECS-specific configurations
│   └── task-definition.json  # ECS task definition
├── scripts/                # AWS deployment and management scripts
│   ├── deploy.sh          # Main deployment script
│   └── setup_aws.sh       # AWS resource setup script
└── README.md              # This file
```

## Key Files

- `ecs/task-definition.json`: Defines how containers should run in ECS
- `scripts/deploy.sh`: Handles building and deploying to ECS
- `scripts/setup_aws.sh`: Sets up required AWS resources

## Usage

1. Set up AWS resources:
```bash
./scripts/setup_aws.sh
```

2. Deploy the application:
```bash
./scripts/deploy.sh
```

## Required AWS Resources

- ECR Repository
- ECS Cluster
- IAM Roles
- CloudWatch Log Group
- SSM Parameter Store 