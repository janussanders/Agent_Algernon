# 🚀 RAG-powered SambaNova Assistant

A sleek Docker-based RAG (Retrieval Augmented Generation) system that provides intelligent querying using SambaNova's API, Qdrant vector storage, and a Streamlit interface.

<p align="center">
  <img src="https://substackcdn.com/image/fetch/w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ffcf74ff5-80e8-4a88-8753-05cfcadfdcb4_1002x622.gif" alt="RAG System" width="800"/>
</p>

# Document Analysis Application
This is a Streamlit-based application for analyzing and querying documents using advanced language models. Here's a breakdown of its main features:

## ✨ Core Features
### **1. Document Analysis**
* Upload PDF and JSON documents
* Process and tokenize documents
* Generate document visualizations using vector embeddings
* Save document chunks to a vector database (Qdrant)

### **2. Interactive Query System**
* Document Chat: Ask questions about the entire document
* Split Analysis: Break down documents into manageable chunks and query individual sections
* Asynchronous streaming responses from LLM (Llama model)
* Session state management to prevent concurrent queries

### **3. Document Processing**
* Automatic text extraction from documents
* Token counting and chunk management
* Support for large documents through chunking
* Vector embeddings for document visualization

## 🚀 AWS Deployment Features
### **1. App Runner Service**
* Automated deployment to AWS App Runner
* Multi-environment support (dev/prod/update)
* Custom domain configuration
* Web ACL integration for security
* VPC connector integration for secure networking
* Automatic cleanup and resource management
* Health check monitoring and status tracking
* Service role and IAM policy management

### **2. Container Management**
* ECR repository setup and management
* Multi-container deployment (Qdrant + RAG app)
* Automated image building and pushing
* Environment-specific configurations
* GPU-optimized Qdrant container support
* Cross-architecture builds (amd64/arm64)
* Automated container cleanup
* Image tag management per environment

### **3. Deployment Tools**
* Deployment scripts for different environments
* Service monitoring and logging
* Clean-up utilities
* Domain configuration tools
* VPC infrastructure management
* Security group configuration
* Network endpoint setup
* Resource state validation

### **4. Network Infrastructure**
* VPC creation and configuration
* Multi-AZ subnet deployment
* Internet Gateway setup
* Route table management
* Security group rules
* VPC endpoint configuration for AWS services
* Private DNS configuration
* Network ACL management

### **5. Security Features**
* Web Application Firewall (WAF) integration
* VPC security group policies
* IAM role-based access control
* ECR repository policies
* VPC endpoint security
* Custom domain SSL/TLS
* Network isolation
* Resource access policies

## 🎯 Technical Features
### Multi-platform Docker Build
* Builds for amd64 and arm64 architectures
* Uses buildx for efficient multi-platform builds

### Asynchronous Processing
* Uses asyncio for non-blocking operations
* Handles streaming responses from the LLM

### State Management
* Manages concurrent queries using session state
* Prevents multiple simultaneous queries
* Maintains document and response history

### Vector Storage
* Integrates with Qdrant vector database
* Stores document chunks with embeddings
* Enables semantic search capabilities

### Token Management
* Handles large documents by chunking
* Processes content in manageable sizes
* Adapts to model context length limits

## 🏗️ AWS Deployment Architecture
### **Infrastructure Components**
1. **VPC Configuration**
   * Multi-AZ subnet architecture
   * Internet Gateway for public access
   * Route tables for traffic management
   * Security groups for access control
   * VPC endpoints for AWS services
   * Private DNS configuration
   * Network ACLs for additional security

2. **Security Layer**
   * Web Application Firewall rules
   * VPC security groups
   * IAM roles and policies
   * SSL/TLS certification
   * Network isolation
   * Resource access control
   * Audit logging

3. **Service Integration**
   * ECR repositories
   * App Runner services
   * CloudWatch logging
   * VPC connectors
   * Load balancing
   * Health monitoring
   * Auto-scaling

### **Benefits**
* Independent scaling and resource optimization
* Isolated deployment and rollback capabilities
* Separate monitoring and logging
* Flexible update strategy
* Optimized build process for each component

### AWS Integration
* ECR image management and versioning
* App Runner service configuration
* Environment-based deployments
* Custom domain handling
* Web ACL security integration

### Deployment Modes
* Development mode with debug features
* Production mode with optimized settings
* Update mode for service modifications
* Environment-specific configurations

## Deployment Process
### Initial Setup
* Configure AWS credentials
* Set environment variables
* Initialize VPC infrastructure
* Create ECR repositories
* Configure IAM roles

### Service Deployment
* Build and push Docker images
* Configure VPC connectors
* Deploy App Runner services
* Set up domain routing
* Configure WAF rules

### Maintenance
* Monitor service health
* Manage resource scaling
* Handle updates and rollbacks
* Clean up unused resources
* Audit security configurations

## Usage Flow
* Upload Document
* Select and upload a document
* System processes and tokenizes content
* Optional visualization generation
## Analysis Options
* Query entire document
* View document splits
* Query individual splits
* Save to vector database
## Query and Response
* Enter queries in text area
* Receive streamed responses
* View and save responses

Manage document chunks
The application provides a comprehensive interface for document analysis, combining the power of large language models with efficient document processing and storage capabilities.

## 📝 License

Apache 2.0

## 🙏 Acknowledgments

- SambaNova API
- Qdrant Vector Database
- Streamlit Framework

---
<p align="center">
  Made with ❤️ by [Janus Sanders/Janus Innovations]
</p>

# RAG Application

A RAG (Retrieval-Augmented Generation) application with Streamlit frontend and Qdrant backend.

## Project Structure

```
.
├── aws/                    # AWS infrastructure and deployment
│   ├── ecs/               # ECS configurations
│   └── scripts/           # AWS deployment scripts
├── config/                # Environment configurations
│   └── env/              # Environment-specific settings
├── docker/               # Docker configurations
│   ├── Dockerfile.local  # Local development Dockerfile
│   ├── Dockerfile.prod   # Production Dockerfile
│   ├── docker-compose.local.yml
│   └── docker-compose.prod.yml
├── src/                  # Application source code
├── tests/               # Test files
├── data/                # Data directory
├── logs/                # Application logs
├── docs/                # Documentation
├── requirements.txt     # Python dependencies
└── scripts/             # Local development scripts
    └── dev.sh          # Local development setup
```

## Development

### Local Development

1. Set up the environment:
```bash
./scripts/dev.sh
```

2. Access the application at http://localhost:8501

### Production Deployment

1. Set up AWS resources:
```bash
./aws/scripts/setup_aws.sh
```

2. Deploy to AWS:
```bash
./aws/scripts/deploy.sh
```

## Environment Variables

The application uses different environment configurations for local and production:

- `config/env/local.env`: Local development settings
- `config/env/prod.env`: Production settings

## Docker

The application uses different Docker configurations for local and production:

- Local: Uses `docker-compose.local.yml` for development
- Production: Uses `docker-compose.prod.yml` for AWS ECS deployment

## AWS Infrastructure

The application is deployed on AWS ECS Fargate with the following components:

- ECR: Container registry for Docker images
- ECS: Container orchestration
- CloudWatch: Logging and monitoring
- SSM: Parameter store for secrets
- IAM: Security and permissions

See `aws/README.md` for more details about the AWS infrastructure.
