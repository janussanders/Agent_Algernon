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

A Retrieval-Augmented Generation (RAG) application built with Streamlit, Qdrant, and Transformers.

## Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose
- Git

## Local Development Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd rag-application
```

2. Make the development script executable:
```bash
chmod +x scripts/dev.sh
```

3. Start the development environment:
```bash
./scripts/dev.sh
```

This script will:
- Create necessary directories (data, logs)
- Set up a Python virtual environment
- Install dependencies
- Start Qdrant in Docker
- Launch the Streamlit application

## Manual Setup

If you prefer to set up manually:

1. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the local environment file:
```bash
cp .env.local .env
```

4. Start Qdrant:
```bash
docker-compose -f docker/docker-compose.local.yml up -d
```

5. Run the application:
```bash
streamlit run src/app.py
```

## Project Structure

```
.
├── data/               # Data storage
│   └── processed/     # Processed documents
├── docker/            # Docker configuration
├── docs/              # Documentation
├── logs/              # Application logs
├── scripts/           # Utility scripts
├── src/               # Source code
│   ├── services/     # Service modules
│   └── app.py        # Main application
├── .env.local        # Local environment variables
├── docker-compose.yml # Docker Compose configuration
└── requirements.txt   # Python dependencies
```

## Development Workflow

1. The application will start with a login screen where you can set up your API key
2. Once logged in, you can:
   - Upload documents
   - Process and visualize documents
   - Chat with the documents
   - Manage your API key

## Troubleshooting

1. If Qdrant fails to start:
   - Check if Docker is running
   - Verify ports 6333 and 6334 are available
   - Check Docker logs: `docker logs rag-qdrant-local`

2. If the application fails to start:
   - Check the logs in `logs/app.log`
   - Verify your API key is set correctly
   - Ensure all dependencies are installed

## Contributing

1. Create a new branch for your feature
2. Make your changes
3. Submit a pull request

## License

[Your License Here]
