#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source utilities and configs
source "${SCRIPT_DIR}/utils.sh"
source "${SCRIPT_DIR}/config.sh"

# Check if deployment mode is provided
if [ -z "$1" ]; then
    log_error "Deployment mode not provided"
    log_warning "Usage: $0 <dev|prod>"
    exit 1
fi

DEPLOY_MODE="$1"
export DEPLOY_MODE

log_warning "Starting ECR cleanup for '${DEPLOY_MODE}' images..."

# Function to delete images in a repository
delete_repository_images() {
    local repo_name="$1"
    log_warning "Checking repository: ${repo_name}"
    
    # Get all image details
    local image_details=$(aws ecr describe-images \
        --repository-name "${repo_name}" \
        --query "imageDetails[*].{digest:imageDigest,tags:imageTags,size:imageSizeInBytes,type:imageType}" \
        --output json)
    
    if [ -z "${image_details}" ] || [ "${image_details}" = "[]" ]; then
        log_warning "No images found in ${repo_name}"
        return 0
    fi
    
    # Count images by type
    local total_images=$(echo "${image_details}" | jq length)
    local tagged_images=$(echo "${image_details}" | jq '[.[] | select(.tags != null)] | length')
    local untagged_images=$(echo "${image_details}" | jq '[.[] | select(.tags == null)] | length')
    
    log_warning "Found ${total_images} total images:"
    log_warning "  - ${tagged_images} tagged images"
    log_warning "  - ${untagged_images} untagged images"
    
    # Create image identifiers array for deletion
    local image_ids="["
    local first=true
    
    while read -r digest; do
        if [ "${first}" = true ]; then
            first=false
        else
            image_ids="${image_ids},"
        fi
        image_ids="${image_ids}{\"imageDigest\":\"${digest}\"}"
    done < <(echo "${image_details}" | jq -r '.[].digest')
    
    image_ids="${image_ids}]"
    
    # Delete all images
    log_warning "Deleting all images..."
    aws ecr batch-delete-image \
        --repository-name "${repo_name}" \
        --image-ids "${image_ids}" \
        --output json
    
    # Verify deletion
    local remaining_count=$(aws ecr describe-images --repository-name "${repo_name}" --query "imageDetails[*].imageDigest" --output text | wc -l)
    if [ "${remaining_count}" -eq 0 ]; then
        log_success "All images deleted from ${repo_name}"
    else
        log_warning "${remaining_count} images remain in ${repo_name}"
    fi
}

# Clean up repository
REPOSITORY="algernon"
if aws ecr describe-repositories --repository-names "${REPOSITORY}" >/dev/null 2>&1; then
    log_warning "Processing repository: ${REPOSITORY}"
    delete_repository_images "${REPOSITORY}"
    
    # Delete the repository if it's empty
    if [ "$(aws ecr describe-images --repository-name "${REPOSITORY}" --query "imageDetails[*].imageDigest" --output text | wc -l)" -eq 0 ]; then
        aws ecr delete-repository --repository-name "${REPOSITORY}" --force --output json
        log_success "Deleted repository: ${REPOSITORY}"
    else
        log_warning "Repository ${REPOSITORY} is not empty, skipping deletion"
    fi
else
    log_warning "Repository ${REPOSITORY} not found, skipping"
fi

log_success "ECR cleanup completed" 