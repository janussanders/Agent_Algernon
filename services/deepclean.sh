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

# Function to clean extended attributes and metadata
clean_metadata() {
    echo "Cleaning up macOS extended attributes and metadata..."

    # Remove extended attributes
    find "$PROJECT_DIR" -type f -exec xattr -c {} + 2>/dev/null || log_warning "Some files may not have extended attributes"

    # Remove .DS_Store files and echo their names
    find "$PROJECT_DIR" -name ".DS_Store" -print -delete

    # Remove AppleDouble files (._*) and echo their names
    find "$PROJECT_DIR" -name "._*" -print -delete

    log_success "Extended attributes and metadata cleanup complete"
}

# Set project directory to the root of the project
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Execute the cleanup
clean_metadata

# Function to print success messages
success() {
    echo -e "\n${GREEN}Cleanup complete!${NC}"
}



