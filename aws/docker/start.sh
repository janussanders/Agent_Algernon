#!/bin/bash

# Function to log with timestamp
log_event() {
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $1"
}

# Function to validate required environment variables
validate_env_vars() {
    local required_vars=(
        "QDRANT_HOST"
        "QDRANT_PORT"
        "QDRANT_GRPC_PORT"
        "STREAMLIT_SERVER_PORT"
        "STREAMLIT_SERVER_ADDRESS"
        "AWS_DEFAULT_REGION"
        "DEPLOY_MODE"
    )
    
    local missing_vars=()
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        log_event "ERROR: Missing required environment variables: ${missing_vars[*]}"
        return 1
    fi
    
    # Log all environment variables for debugging
    log_event "Environment variables:"
    env | sort | while read -r line; do
        # Mask sensitive values
        if [[ $line == *"KEY"* ]] || [[ $line == *"SECRET"* ]] || [[ $line == *"PASSWORD"* ]]; then
            var_name=$(echo "$line" | cut -d= -f1)
            log_event "$var_name=********"
        else
            log_event "$line"
        fi
    done
    
    return 0
}

log_event "=== Starting deployment sequence ==="
log_event "Container environment initialized"

# Validate environment variables first
if ! validate_env_vars; then
    log_event "FATAL: Environment validation failed"
    exit 1
fi

# Create Qdrant config dynamically
log_event "Creating Qdrant configuration..."
mkdir -p /app/qdrant
cat > /app/qdrant/config.yaml << EOF
storage:
  storage_path: /app/qdrant/storage
service:
  http_port: ${QDRANT_PORT}
  grpc_port: ${QDRANT_GRPC_PORT}
  # Allow connections from Streamlit in the same container
  host: 0.0.0.0
telemetry:
  disabled: true
EOF
log_event "Qdrant configuration created"

# Start Qdrant in the background
log_event "Starting Qdrant service..."
qdrant --config-path /app/qdrant/config.yaml &
QDRANT_PID=$!
log_event "Qdrant process started with PID: ${QDRANT_PID}"

# Function to check if a port is accepting connections
check_port() {
    local host=$1
    local port=$2
    local service=$3
    local max_attempts=$4
    local attempt=1
    
    while ! nc -z "${host}" "${port}"; do
        if [ ${attempt} -ge ${max_attempts} ]; then
            log_event "ERROR: ${service} failed to start on ${host}:${port} after ${max_attempts} attempts"
            return 1
        fi
        log_event "Waiting for ${service} to be ready on ${host}:${port} (attempt ${attempt}/${max_attempts})"
        sleep 2
        attempt=$((attempt + 1))
    done
    log_event "${service} is ready on ${host}:${port}"
    return 0
}

# Check if Qdrant is running and accepting connections
if ! check_port "${QDRANT_HOST}" "${QDRANT_PORT}" "Qdrant HTTP" 30; then
    log_event "FATAL: Qdrant HTTP service failed to start"
    exit 1
fi

if ! check_port "${QDRANT_HOST}" "${QDRANT_GRPC_PORT}" "Qdrant gRPC" 30; then
    log_event "FATAL: Qdrant gRPC service failed to start"
    exit 1
fi

# Verify Qdrant is responding to API requests
log_event "Verifying Qdrant API health..."
QDRANT_HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" "http://${QDRANT_HOST}:${QDRANT_PORT}/healthz")
if [ "${QDRANT_HEALTH_CHECK}" = "200" ]; then
    log_event "SUCCESS: Qdrant API is healthy"
else
    log_event "ERROR: Qdrant API health check failed with status ${QDRANT_HEALTH_CHECK}"
    exit 1
fi

# Log Qdrant version and status
QDRANT_VERSION=$(curl -s "http://${QDRANT_HOST}:${QDRANT_PORT}/version" | jq -r '.version')
log_event "Qdrant version ${QDRANT_VERSION} is running"

# Write ready file for App Runner health check
touch /tmp/qdrant_ready
log_event "Qdrant ready file created at /tmp/qdrant_ready"

# Start the RAG app with Streamlit
log_event "Starting Streamlit application..."
log_event "Streamlit configuration:"
log_event "- Server port: ${STREAMLIT_SERVER_PORT}"
log_event "- Server address: ${STREAMLIT_SERVER_ADDRESS}"
log_event "- Environment: ${DEPLOY_MODE}"

# Export additional environment variables for Streamlit
export QDRANT_URL="http://${QDRANT_HOST}:${QDRANT_PORT}"
export QDRANT_GRPC_URL="${QDRANT_HOST}:${QDRANT_GRPC_PORT}"

# Monitor processes
monitor_processes() {
    while true; do
        # Check Qdrant
        if ! kill -0 ${QDRANT_PID} 2>/dev/null; then
            log_event "FATAL: Qdrant process died unexpectedly"
            rm -f /tmp/qdrant_ready
            kill -TERM $$
        fi
        
        # Check Streamlit
        if [ -n "${STREAMLIT_PID}" ] && ! kill -0 ${STREAMLIT_PID} 2>/dev/null; then
            log_event "FATAL: Streamlit process died unexpectedly"
            rm -f /tmp/qdrant_ready
            kill -TERM $$
        fi
        
        sleep 5
    done
}

# Start Streamlit
log_event "Executing Streamlit..."
streamlit run --server.port "${STREAMLIT_SERVER_PORT}" --server.address "${STREAMLIT_SERVER_ADDRESS}" src/app.py &
STREAMLIT_PID=$!
log_event "Streamlit process started with PID: ${STREAMLIT_PID}"

# Start process monitor in background
monitor_processes &

# Wait for any process to exit
wait -n

# If we get here, one of the processes died
log_event "FATAL: A monitored process has exited"
rm -f /tmp/qdrant_ready
exit 1 