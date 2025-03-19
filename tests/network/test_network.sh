#!/bin/bash

# Source the utils script for logging functions
source "$(dirname "$0")/../../services/utils.sh"

# Source AWS configuration
source "$(dirname "$0")/../../aws/config.sh"

# Function to test connection with timeout
test_connection_timeout() {
    local host="$1"
    local port="$2"
    local timeout="$3"
    
    info "Testing TCP connection to ${host}:${port} (timeout: ${timeout}s)..."
    if nc -zv -w"${timeout}" "${host}" "${port}" 2>&1; then
        success "TCP connection successful to ${host}:${port}"
        return 0
    else
        error "TCP connection failed to ${host}:${port}"
        return 1
    fi
}

# Function to test DNS resolution with detailed output
test_dns() {
    local host="$1"
    local service="$2"
    
    info "Testing DNS resolution for ${service} (${host})..."
    
    # Try dig first
    if command -v dig >/dev/null 2>&1; then
        info "DNS lookup using dig:"
        dig +short "${host}" || true
    fi
    
    # Try nslookup as backup
    info "DNS lookup using nslookup:"
    nslookup "${host}" || true
    
    # Test actual resolution
    if host "${host}" > /dev/null 2>&1; then
        success "DNS resolution successful for ${host}"
        return 0
    else
        error "DNS resolution failed for ${host}"
        return 1
    fi
}

# Function to test network route
test_route() {
    local host="$1"
    local service="$2"
    
    info "Testing network route to ${service} (${host})..."
    
    # Show route
    info "Route to host:"
    traceroute -n "${host}" 2>&1 || true
    
    # Test basic connectivity
    if ping -c 3 -W 5 "${host}" > /dev/null 2>&1; then
        success "Route to ${host} is accessible"
        return 0
    else
        error "Route to ${host} is not accessible"
        return 1
    fi
}

# Function to test HTTP API with detailed diagnostics
test_http_api() {
    local host="$1"
    local port="$2"
    local service="$3"
    local endpoint="${4:-/healthz}"
    
    info "Testing ${service} HTTP API on ${host}:${port}${endpoint}..."
    
    # First test TCP connection
    if ! test_connection_timeout "${host}" "${port}" 5; then
        error "TCP connection failed, skipping HTTP test"
        return 1
    fi
    
    # Use curl with verbose output for debugging
    local response
    response=$(curl -v -s -w "\nHTTP_CODE: %{http_code}\n" "https://${host}${endpoint}" 2>&1)
    local status_code=$(echo "${response}" | grep "HTTP_CODE:" | cut -d' ' -f2)
    
    info "Connection details:"
    echo "${response}" | grep -E "^\* " || true
    
    if [ "${status_code}" = "200" ]; then
        success "${service} HTTP API is accessible"
        return 0
    else
        error "${service} HTTP API returned status ${status_code}"
        info "Response headers:"
        echo "${response}" | grep -E "^< " || true
        return 1
    fi
}

# Function to test WebSocket connectivity
test_websocket() {
    local host="$1"
    local port="$2"
    local service="$3"
    
    info "Testing WebSocket connection to ${service} (${host}:${port})..."
    
    # Test WebSocket connection using curl
    if curl -v -N -H "Connection: Upgrade" \
           -H "Upgrade: websocket" \
           -H "Host: ${host}" \
           -H "Origin: https://${host}" \
           "wss://${host}:${port}/_stcore/stream" 2>&1 | grep -q "101 Switching Protocols"; then
        success "WebSocket connection successful to ${service}"
        return 0
    else
        error "WebSocket connection failed to ${service}"
        return 1
    fi
}

# Function to test network latency with statistics
test_latency() {
    local host="$1"
    local service="$2"
    
    info "Testing network latency to ${service} (${host})..."
    
    # Detailed ping with statistics
    if ping -c 5 -i 0.2 "${host}" > /dev/null 2>&1; then
        local ping_stats=$(ping -c 5 -i 0.2 "${host}" | grep -E "rtt|packets")
        success "Network latency test successful"
        info "Ping statistics:"
        echo "${ping_stats}"
        return 0
    else
        error "Network latency test failed"
        return 1
    fi
}

# Function to test RAG to Qdrant communication
test_rag_qdrant_communication() {
    local rag_host="$1"
    local qdrant_host="$2"
    
    info "Testing RAG App to Qdrant communication..."
    
    # Test if RAG app can reach Qdrant
    info "Testing RAG App's ability to reach Qdrant..."
    local response
    response=$(curl -v -s -w "\nHTTP_CODE: %{http_code}\n" \
        "https://${rag_host}/_stcore/health" \
        -H "X-Qdrant-Host: ${qdrant_host}" \
        2>&1)
    
    local status_code=$(echo "${response}" | grep "HTTP_CODE:" | cut -d' ' -f2)
    
    if [ "${status_code}" = "200" ]; then
        success "RAG App can reach Qdrant"
        return 0
    else
        error "RAG App cannot reach Qdrant (Status: ${status_code})"
        info "Response details:"
        echo "${response}" | grep -E "^\* |^< " || true
        return 1
    fi
}

# Main testing function for AWS environment
test_aws_environment() {
    info "Starting comprehensive network tests for AWS environment..."
    
    # Validate required environment variables
    if [ -z "${QDRANT_HOST}" ]; then
        error "QDRANT_HOST not set in aws/config.sh"
        exit 1
    fi
    
    if [ -z "${RAG_APP_HOST}" ]; then
        error "RAG_APP_HOST not set in aws/config.sh"
        exit 1
    fi
    
    info "Using endpoints from config.sh:"
    info "  QDRANT_HOST: ${QDRANT_HOST}"
    info "  RAG_APP_HOST: ${RAG_APP_HOST}"
    
    # Test DNS resolution
    test_dns "${QDRANT_HOST}" "Qdrant"
    test_dns "${RAG_APP_HOST}" "RAG App"
    
    # Test routes
    test_route "${QDRANT_HOST}" "Qdrant"
    test_route "${RAG_APP_HOST}" "RAG App"
    
    # Test Qdrant endpoints
    info "Testing Qdrant endpoints..."
    test_http_api "${QDRANT_HOST}" "443" "Qdrant" "/healthz"
    test_http_api "${QDRANT_HOST}" "443" "Qdrant" "/collections"
    
    # Test RAG App endpoints
    info "Testing RAG App endpoints..."
    test_http_api "${RAG_APP_HOST}" "443" "RAG App" "/healthz"
    test_http_api "${RAG_APP_HOST}" "443" "RAG App" "/_stcore/health"
    
    # Test RAG to Qdrant communication
    test_rag_qdrant_communication "${RAG_APP_HOST}" "${QDRANT_HOST}"
    
    # Test WebSocket connections (Streamlit internal)
    info "Testing Streamlit WebSocket connections..."
    test_websocket "${RAG_APP_HOST}" "443" "RAG App"
    
    # Test latency
    test_latency "${QDRANT_HOST}" "Qdrant"
    test_latency "${RAG_APP_HOST}" "RAG App"
    
    # Show network interface information
    info "Network interface information:"
    ip addr show || ifconfig
    
    # Show current connections
    info "Current network connections:"
    netstat -tuln || ss -tuln
}

# Main execution
if [ "$1" = "aws" ]; then
    test_aws_environment
else
    error "This version of the test script is for AWS production testing only"
    error "Usage: $0 aws"
    exit 1
fi 