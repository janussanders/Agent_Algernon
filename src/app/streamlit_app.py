import os
import tempfile
from pathlib import Path
from loguru import logger
import streamlit as st
from datetime import datetime
import json
import numpy as np
import asyncio
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, HnswConfigDiff
import re
import plotly.express as px

from src.document_processor import DocumentProcessor
from src.utils import create_streaming_chat_completion, validate_sambanova_setup
from src.vector_store import VectorStore

class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder for numpy types"""
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return super().default(obj)

def connect_to_qdrant(max_retries=5, retry_delay=5):
    """Connect to Qdrant with retries"""
    qdrant_host = os.getenv("QDRANT_HOST")
    if not qdrant_host:
        raise ValueError("QDRANT_HOST environment variable must be set")
        
    # Use HTTPS if configured
    qdrant_https = os.getenv("QDRANT_HTTPS", "false").lower() == "true"
    qdrant_url = f"https://{qdrant_host}" if qdrant_https else f"http://{qdrant_host}"
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to Qdrant at: {qdrant_url}:{qdrant_port} (Attempt {attempt + 1}/{max_retries})")
            client = QdrantClient(
                url=qdrant_url,
                port=qdrant_port,
                timeout=30.0,
                prefer_grpc=False,  # Use HTTP in App Runner
                verify=False  # Skip SSL verification for internal VPC communication
            )
            # Test the connection
            client.get_collections()
            logger.info("Successfully connected to Qdrant")
            return client
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Failed to connect to Qdrant: {str(e)}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect to Qdrant after {max_retries} attempts: {str(e)}")
                raise

class StreamlitApp:
    def __init__(self):
        self.vector_store = VectorStore()
        self.document_processor = DocumentProcessor()
        self.setup_page_config()
        self.setup_session_state()
        
    def setup_page_config(self):
        st.set_page_config(
            page_title="Algernon - Document Analysis & Chat",
            page_icon="🤖",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
    def setup_session_state(self):
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        if 'current_document' not in st.session_state:
            st.session_state.current_document = None
        if 'document_chunks' not in st.session_state:
            st.session_state.document_chunks = []
        if 'is_authenticated' not in st.session_state:
            st.session_state.is_authenticated = False
        if 'api_key' not in st.session_state:
            st.session_state.api_key = None
        if 'password' not in st.session_state:
            st.session_state.password = None
        if 'selected_model' not in st.session_state:
            st.session_state.selected_model = "DeepSeek-R1-Distill-Llama-70B"
        if 'temperature' not in st.session_state:
            st.session_state.temperature = 0.7
        if 'max_tokens' not in st.session_state:
            st.session_state.max_tokens = 1000
        if 'top_p' not in st.session_state:
            st.session_state.top_p = 0.9
            
    def render_login(self):
        st.title("Welcome to Algernon")
        
        if not st.session_state.api_key:
            st.write("Please enter your SambaNova API key to continue")
            api_key = st.text_input("SambaNova API Key", type="password")
            if st.button("Save API Key"):
                if not api_key:
                    st.error("Please enter an API key")
                    return
                    
                try:
                    if validate_sambanova_setup(api_key):
                        st.session_state.api_key = api_key
                        st.success("API key saved successfully!")
                        st.rerun()
                    else:
                        st.error("Invalid API key or connection failed. Please check your API key and try again.")
                except Exception as e:
                    logger.error(f"Error during API key validation: {str(e)}")
                    st.error("An error occurred while validating the API key. Please try again.")
        else:
            st.write("Please enter your password to continue")
            password = st.text_input("Password", type="password")
            if st.button("Login"):
                if not password:
                    st.error("Please enter a password")
                    return
                    
                try:
                    # Store password in session state
                    st.session_state.password = password
                    st.session_state.is_authenticated = True
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error during login: {str(e)}")
                    st.error("An error occurred during login. Please try again.")
                    
    def render_sidebar(self):
        with st.sidebar:
            st.title("Settings")
            
            # SambaNova Model Settings
            st.subheader("Model Settings")
            
            # Define available models
            model_options = [
                "DeepSeek-R1-Distill-Llama-70B",
                "DeepSeek-R1",
                "Llama-3.1-Tulu-3-405B",
                "Meta-Llama-3.3-70B-Instruct",
                "Meta-Llama-3.1-405B-Instruct",
                "Meta-Llama-2-70B-Chat",
                "Meta-Llama-2-13B-Chat",
                "Meta-Llama-2-7B-Chat"
            ]
            
            # Model selection
            st.session_state.selected_model = st.selectbox(
                "Select Model",
                options=model_options,
                index=model_options.index(st.session_state.selected_model),
                key="model_selector"
            )
            
            st.session_state.temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=st.session_state.temperature,
                step=0.1
            )
            
            st.session_state.max_tokens = st.slider(
                "Max Tokens",
                min_value=100,
                max_value=4000,
                value=st.session_state.max_tokens,
                step=100
            )
            
            st.session_state.top_p = st.slider(
                "Top P",
                min_value=0.0,
                max_value=1.0,
                value=st.session_state.top_p,
                step=0.1
            )
            
            # Document Upload
            st.subheader("Document Upload")
            uploaded_file = st.file_uploader(
                "Upload a document",
                type=["pdf"],
                help="Upload a PDF document to analyze"
            )
            
            if uploaded_file:
                try:
                    # Save uploaded file temporarily
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = tmp_file.name
                    
                    # Process document
                    text = self.document_processor.extract_text(tmp_file_path)
                    st.session_state.current_document = text
                    
                    # Process document into chunks
                    chunks = self.vector_store.process_document(text)
                    st.session_state.document_chunks = chunks
                    
                    st.success("Document processed successfully!")
                    
                except Exception as e:
                    st.error(f"Error processing document: {str(e)}")
                    logger.error(f"Error processing document: {str(e)}")
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(tmp_file_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary file: {str(e)}")
            
            if st.button("Clear Chat History"):
                st.session_state.messages = []
                st.rerun()
                
            if st.button("Logout"):
                st.session_state.is_authenticated = False
                st.session_state.messages = []
                st.rerun()
                
    def render_chat_interface(self):
        st.title("Chat with Algernon")
        
        # Display chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
        # Chat input
        if prompt := st.chat_input("What would you like to know?"):
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
                
            # Display assistant response
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""
                
                # Prepare context based on whether a document is loaded
                messages = st.session_state.messages
                if st.session_state.current_document:
                    # Add document context for RAG
                    messages = [
                        {"role": "system", "content": "You are analyzing the uploaded document. Use the document context to answer questions."},
                        {"role": "user", "content": f"Document context: {st.session_state.current_document[:1000]}..."},
                        *st.session_state.messages
                    ]
                
                # Stream the response
                for response_chunk in create_streaming_chat_completion(
                    messages=messages,
                    model=st.session_state.selected_model,
                    temperature=st.session_state.temperature,
                    max_tokens=st.session_state.max_tokens,
                    top_p=st.session_state.top_p,
                    stream=True
                ):
                    full_response += response_chunk
                    message_placeholder.markdown(full_response + "▌")
                    
                message_placeholder.markdown(full_response)
                
            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": full_response})
                
    def run(self):
        if not st.session_state.is_authenticated:
            self.render_login()
        else:
            self.render_sidebar()
            self.render_chat_interface()
                
def main():
    app = StreamlitApp()
    app.run()
    
if __name__ == "__main__":
    main() 