#!/bin/bash

# Start Qdrant in the background
qdrant &

# Wait for Qdrant to start using the same health check as docker-compose
until curl -sf http://localhost:6333/healthz > /dev/null; do
    echo "Waiting for Qdrant health check..."
    sleep 5
done

# Additional check for GRPC port
until nc -z localhost 6334; do
    echo "Waiting for Qdrant GRPC to start..."
    sleep 2
done

# Additional check for P2P port
until nc -z localhost 6335; do
    echo "Waiting for Qdrant P2P to start..."
    sleep 2
done

echo "Qdrant is fully initialized and ready!" 