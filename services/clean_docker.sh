#!/bin/bash

# Set error handling
set -e
trap 'echo "Error on line $LINENO"' ERR

# Source the utils script for logging functions
source "$(dirname "$0")/utils.sh"

# Function to get Docker disk usage
get_docker_disk_usage() {
    docker system df --format "{{.Size}}" | head -n 1
}

# Function to convert size to bytes
convert_to_bytes() {
    local size="$1"
    local number=$(echo "$size" | sed 's/[^0-9.]//g')
    local unit=$(echo "$size" | sed 's/[0-9.]//g')
    
    case "$unit" in
        "GB")
            echo "$number * 1024 * 1024 * 1024" | bc
            ;;
        "MB")
            echo "$number * 1024 * 1024" | bc
            ;;
        "KB")
            echo "$number * 1024" | bc
            ;;
        "B")
            echo "$number"
            ;;
        *)
            echo "0"
            ;;
    esac
}

# Function to convert bytes to human readable format
bytes_to_human() {
    local bytes="$1"
    
    if (( $(echo "$bytes >= 1073741824" | bc -l) )); then
        echo "scale=2; $bytes/1073741824" | bc | sed 's/\.00$//' | tr -d '\n' && echo "GB"
    elif (( $(echo "$bytes >= 1048576" | bc -l) )); then
        echo "scale=2; $bytes/1048576" | bc | sed 's/\.00$//' | tr -d '\n' && echo "MB"
    elif (( $(echo "$bytes >= 1024" | bc -l) )); then
        echo "scale=2; $bytes/1024" | bc | sed 's/\.00$//' | tr -d '\n' && echo "KB"
    else
        echo "${bytes}B"
    fi
}

# Function to clean up Docker containers and artifacts
clean_docker() {
    # Get initial disk usage
    initial_usage=$(get_docker_disk_usage)
    warn "Initial Docker disk usage: ${initial_usage}"

    warn "Purging all Docker containers and artifacts..."

    # Stop all running containers
    warn "Stopping running containers..."
    docker ps -q | xargs -r docker stop

    # Remove all containers (including stopped ones)
    warn "Removing all containers..."
    docker ps -a -q | xargs -r docker rm -f

    # Remove all images
    warn "Removing all images..."
    docker images -q | xargs -r docker rmi -f

    # Remove all user-defined networks
    warn "Removing custom networks..."
    docker network ls --filter type=custom -q | xargs -r docker network rm -f

    # Remove all volumes
    warn "Removing all volumes..."
    docker volume ls -q | xargs -r docker volume rm -f

    # Clean up build cache
    warn "Cleaning build cache..."
    docker builder prune -af --filter until=24h

    # System prune to remove all unused data
    warn "Performing system prune..."
    docker system prune -af --volumes

    # Get final disk usage
    final_usage=$(get_docker_disk_usage)
    
    # Calculate space saved
    initial_bytes=$(convert_to_bytes "$initial_usage")
    final_bytes=$(convert_to_bytes "$final_usage")
    saved_bytes=$(echo "$initial_bytes - $final_bytes" | bc)
    saved_space=$(bytes_to_human "$saved_bytes")

    success "Docker cleanup complete"
    info "Final Docker disk usage: ${final_usage}"
    success "Space recovered: ${saved_space}"
}

# Execute the cleanup
clean_docker