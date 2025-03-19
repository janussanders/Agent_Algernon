#!/bin/bash

# Set up local environment
python3 scripts/env_manager.py local

# Build and start the development environment
docker-compose -f docker/docker-compose.local.yml up -d

# Watch for changes in src directory
docker-compose -f docker/docker-compose.local.yml exec rag-app streamlit run src/main.py --server.runOnSave true 