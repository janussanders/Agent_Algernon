#!/bin/bash

# Define project directory and paths
PROJECT_DIR="."
DOCKER_COMPOSE="$PROJECT_DIR/docker/docker-compose.yml"

# Import color and message functions
source ./services/utils.sh

echo "Starting RAG system setup..."

# 1. Set permissions first
if ! ./set_permissions.sh; then
    error "Failed to set permissions"
    exit 1
fi

# 2. Clean up any existing containers and volumes
if ! ./services/clean_docker.sh; then
    error "Failed to clean up existing containers"
    exit 1
fi

# 3. Start basic services (Ollama)
if ! ./services/start_services.sh; then
    error "Failed to start basic services"
    exit 1
fi



# 4. Start Qdrant separately
if ! ./services/start_qdrant.sh; then
    error "Failed to start Qdrant"
    exit 1
fi


if ! curl -s -f "http://localhost:6333/collections" > /dev/null; then
    error "Qdrant is not responding"
    exit 1
fi

success "Setup complete!"