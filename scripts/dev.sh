#!/bin/bash

# Exit on error
set -e

echo "Setting up RAG application development environment..."

# Create necessary directories
echo "Creating directories..."
mkdir -p data/processed logs

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Copy environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating environment file..."
    cp .env.local .env
fi

# Start Qdrant
echo "Starting Qdrant..."
docker-compose -f docker/docker-compose.local.yml up -d

# Wait for Qdrant to be ready
echo "Waiting for Qdrant to be ready..."
until curl -s http://localhost:6333/healthz > /dev/null; do
    echo "Waiting for Qdrant..."
    sleep 2
done
echo "Qdrant is ready!"

# Function to cleanup on exit
cleanup() {
    echo "Stopping Qdrant..."
    docker-compose -f docker/docker-compose.local.yml down
    echo "Deactivating virtual environment..."
    deactivate
}

# Set up cleanup on exit
trap cleanup EXIT

# Start the application
echo "Starting Streamlit application..."
streamlit run src/app.py 