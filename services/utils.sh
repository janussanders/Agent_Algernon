#!/bin/bash

# Define color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Define utility functions for consistent messaging
error() { 
    echo -e "${RED}✗ $1${NC}" >&2
}

success() { 
    echo -e "${GREEN}✓ $1${NC}"
}

warn() { 
    echo -e "${YELLOW}! $1${NC}"
}

info() {
    echo -e "${BLUE}$1${NC}"
} 