#!/usr/bin/env python3

import os
from pathlib import Path
from loguru import logger

def create_env_file():
    """Create .env file with required variables"""
    
    # Check for existing API key in current .env
    existing_api_key = None
    env_path = Path(".env")
    if env_path.exists():
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('SAMBANOVA_API_KEY='):
                        existing_api_key = line.split('=')[1].strip()
                        break
        except Exception as e:
            logger.warning(f"Could not read existing .env file: {e}")
    
    env_template = {
        "SAMBANOVA_API_KEY": existing_api_key or "",
        "SAMBANOVA_URL": "https://api.sambanova.ai/v1",  # Updated URL
        "DEBUG": "true",
        "STREAMLIT_DEBUG": "true",
        "PYTHONPATH": "/app",
        "QDRANT_HOST": "qdrant",
        "QDRANT_PORT": "6333",
        "STREAMLIT_SERVER_ADDRESS": "0.0.0.0",
        "STREAMLIT_SERVER_PORT": "8501"
    }
    
    try:
        # Only prompt for API key if not found in existing .env
        if not env_template["SAMBANOVA_API_KEY"]:
            api_key = input("Enter your SambaNova API key: ").strip()
            if not api_key:
                raise ValueError("API key cannot be empty")
            env_template["SAMBANOVA_API_KEY"] = api_key
        else:
            logger.info("Using existing API key from .env file")
        
        # Write environment file to both project root and app directory
        with open(env_path, "w") as f:
            for key, value in env_template.items():
                f.write(f"{key}={value}\n")
        
        # Also write to /app/.env for Docker container
        app_env_path = Path("/app/.env")
        if app_env_path.parent.exists():
            with open(app_env_path, "w") as f:
                for key, value in env_template.items():
                    f.write(f"{key}={value}\n")
        
        # Set variables in current environment
        os.environ.update(env_template)
        
        logger.success("Environment file created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create environment file: {str(e)}")
        return False

if __name__ == "__main__":
    if not create_env_file():
        exit(1)
    exit(0) 