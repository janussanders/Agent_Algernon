# Development Guide

## Prerequisites

- Python 3.11+
- Docker and Docker Compose
- AWS CLI (for deployment)
- Git

## Local Development Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd rag-app
```

### 2. Set Up Environment

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy example environment file
cp config/env/local.env.example config/env/local.env

# Edit local.env with your settings
```

### 4. Start Development Environment

```bash
# Start services using Docker Compose
./scripts/dev.sh
```

The application will be available at http://localhost:8501

## Development Workflow

### 1. Code Style

- Follow PEP 8 guidelines
- Use type hints
- Write docstrings for functions and classes
- Keep functions focused and small

### 2. Testing

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_app.py
```

### 3. Linting

```bash
# Run linters
flake8 src/ tests/
black src/ tests/
isort src/ tests/
```

### 4. Logging

- Use structured logging
- Include relevant context in log messages
- Use appropriate log levels:
  - DEBUG: Detailed information
  - INFO: General information
  - WARNING: Potential issues
  - ERROR: Errors that need attention
  - CRITICAL: Critical issues

Example:
```python
import logging

logging.info("Processing document", extra={
    "document_id": doc_id,
    "file_name": file_name,
    "file_size": file_size
})
```

## Docker Development

### 1. Building Images

```bash
# Build local development image
docker-compose -f docker/docker-compose.local.yml build

# Build production image
docker-compose -f docker/docker-compose.prod.yml build
```

### 2. Running Containers

```bash
# Start local development environment
docker-compose -f docker/docker-compose.local.yml up

# Start production environment
docker-compose -f docker/docker-compose.prod.yml up
```

### 3. Debugging

```bash
# View logs
docker-compose -f docker/docker-compose.local.yml logs -f

# Access container shell
docker-compose -f docker/docker-compose.local.yml exec rag-app bash
```

## AWS Deployment

### 1. AWS Setup

```bash
# Configure AWS credentials
aws configure

# Set up AWS resources
./aws/scripts/setup_aws.sh
```

### 2. Deployment

```bash
# Deploy to AWS
./aws/scripts/deploy.sh
```

### 3. Monitoring

```bash
# View CloudWatch logs
aws logs tail /ecs/rag-task --follow

# Check service status
aws ecs describe-services --cluster rag-cluster --services rag-service
```

## Common Issues and Solutions

### 1. Docker Issues

- **Container won't start**: Check logs with `docker-compose logs`
- **Volume mount issues**: Ensure correct permissions
- **Network issues**: Check Docker network configuration

### 2. AWS Issues

- **Permission errors**: Verify IAM roles and policies
- **Deployment failures**: Check ECS task definition
- **Logging issues**: Verify CloudWatch configuration

### 3. Application Issues

- **WebSocket connection**: Check network configuration
- **Qdrant connection**: Verify service discovery
- **API errors**: Check API key configuration

## Best Practices

### 1. Code Organization

- Keep related code together
- Use clear module names
- Maintain separation of concerns
- Follow the project structure

### 2. Error Handling

- Use try-except blocks appropriately
- Log errors with context
- Implement graceful degradation
- Provide user-friendly error messages

### 3. Performance

- Optimize database queries
- Use caching where appropriate
- Implement pagination for large datasets
- Monitor resource usage

### 4. Security

- Never commit sensitive data
- Use environment variables for secrets
- Implement proper authentication
- Follow security best practices

## Contributing

### 1. Pull Request Process

1. Create a feature branch
2. Make your changes
3. Run tests and linting
4. Update documentation
5. Submit pull request

### 2. Code Review

- Review code changes
- Check test coverage
- Verify documentation
- Ensure security compliance

### 3. Documentation

- Update relevant documentation
- Add inline comments
- Update README if needed
- Document new features

## Support

- Check the documentation
- Review common issues
- Contact the development team
- Submit bug reports 