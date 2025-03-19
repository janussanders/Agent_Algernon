#!/bin/bash

# Set error handling
set -e
trap 'echo "Error on line $LINENO"' ERR

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Helper functions
log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_warning() { echo -e "${YELLOW}! $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}" >&2; }

# Setup environment variables
echo "Setting up environment variables..."
if [ ! -f ".env" ]; then
    log_warning "No .env file found. Creating from template..."
    if [ -f "setup_env.py" ]; then
        python3 setup_env.py
        if [ $? -ne 0 ]; then
            log_error "Failed to create .env file"
            exit 1
        fi
        log_success "Environment file created"
    else
        log_error "setup_env.py not found"
        exit 1
    fi
fi

# Source the environment variables
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    log_success "Environment variables loaded"
else
    log_error "Environment file not found"
    exit 1
fi

echo "Starting RAG services..."
echo "Verifying clean state..."
# Verify clean state
if [ -f "docker/._Dockerfile" ] || [ -f "docker/._docker-compose.yml" ] || [ -f "._docker" ]; then
    log_warning "Running environment cleanup..."
    ./services/deepclean.sh
    log_success "Cleanup complete"
fi

# Clean up macOS metadata files
echo "Cleaning up additionalmacOS metadata..."
find . -name "._*" -delete
find . -name ".DS_Store" -delete
log_success "Additional Metadata cleanup complete"

# Start services with docker-compose
echo "Building and starting containers..."
docker-compose -f docker/docker-compose.yml up -d --build \
    --force-recreate

# Verify services started
echo "Verifying services..."
docker-compose -f docker/docker-compose.yml ps

log_success "Services started successfully!"