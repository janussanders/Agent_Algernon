#!/bin/bash

# Source utility functions if available
if [ -f "./services/utils.sh" ]; then
    source ./services/utils.sh
else
    error "utils.sh not found in services directory"
    exit 1
fi

# Set strict error handling
set -e
trap 'echo "Error on line $LINENO"' ERR

# Define project directories and paths
PROJECT_DIR="."

# Define project directories to process
DIRECTORIES=(
    "docker"
    "services"
    "src"
    "tests"
    "data"
    "qdrant_storage"
    "docs"
    "logs"
)

set_permissions() {
    local dir="$1"
    
    # Set permissions for all files and directories
    find "$dir" -type d | while read -r subdir; do
        # Set standard permissions for items in this subdirectory
        find "$subdir" -maxdepth 1 -type f -exec chmod 644 {} \;
        find "$subdir" -maxdepth 1 -type d -exec chmod 755 {} \;
        
        # Make all .sh files executable in this subdirectory
        find "$subdir" -maxdepth 1 -name "*.sh" -type f -exec chmod +x {} \;
    done
}

check_directory() {
    if [ ! -d "$1" ]; then
        echo "Creating directory: $1"
        mkdir -p "$1"
    fi
}

set_docker_permissions() {
    if [ -d "$PROJECT_DIR/docker" ]; then
        echo "Setting Docker file permissions..."
        chmod 755 "$PROJECT_DIR/docker"
        chmod 644 "$PROJECT_DIR/docker/Dockerfile" "$PROJECT_DIR/docker/docker-compose.yml" "$PROJECT_DIR/docker/.dockerignore" 2>/dev/null || true
    fi
}

echo -e "${BLUE}Setting up permissions for RAG project...${NC}"

# Docker configuration check
if ! docker info >/dev/null 2>&1; then
    warn "Docker daemon is not running or you don't have sufficient permissions"
fi

# Create and process directories
for dir in "${DIRECTORIES[@]}"; do
    check_directory "$PROJECT_DIR/$dir"
    if [ -d "$dir" ]; then
        set_permissions "$dir"
    else
        warn "Directory $dir not found, skipping..."
    fi
done

# Special handling for docker files
set_docker_permissions

success "All permissions have been set successfully"

exit 0