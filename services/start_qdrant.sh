#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Function to print success messages
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error messages
error() {
    echo -e "${RED}✗ $1${NC}"
}

echo "Starting Qdrant setup..."

# Check container status
CONTAINER_ID=$(docker ps -q --filter name=qdrant)
if [ -z "$CONTAINER_ID" ]; then
    error "Container failed to start"
    exit 1
fi

# Check if Qdrant is responding
if curl -s -f "http://localhost:6333/collections" > /dev/null; then
    success "Qdrant is running and responding"
else
    error "Qdrant failed to start properly"
    docker logs $CONTAINER_ID
    exit 1
fi

success "Qdrant setup complete!"