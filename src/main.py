#!/usr/bin/env python3

import os
import sys
from pathlib import Path
from loguru import logger
import streamlit as st

# Configure logging
logger.remove()
logger.add(
    "logs/app.log",
    rotation="500 MB",
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    enqueue=True
)
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    enqueue=True
)

# Import our Streamlit app
from src.app import StreamlitApp

def main():
    """Main entry point for the application"""
    try:
        logger.info("Starting application...")
        logger.info(f"QDRANT_HOST: {os.getenv('QDRANT_HOST', 'not set')}")
        logger.info(f"SAMBANOVA_URL: {os.getenv('SAMBANOVA_URL', 'not set')}")
        logger.info(f"WEBSOCKET_API_URL: {os.getenv('WEBSOCKET_API_URL', 'not set')}")
        
        # Initialize and run the app
        logger.info("Initializing Streamlit app...")
        app = StreamlitApp()
        logger.info("Rendering Streamlit app...")
        app.render()
        logger.info("Application startup complete")

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        st.error(f"An error occurred: {str(e)}")
        # Log full traceback for debugging
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")

if __name__ == "__main__":
    main()
