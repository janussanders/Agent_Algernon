import os
import tempfile
from pathlib import Path
from loguru import logger
import streamlit as st
from src.document_processor import DocumentProcessor
from src.utils import create_streaming_chat_completion, validate_sambanova_setup
from src.vector_store import VectorStore
from src.config import config
from datetime import datetime
import json
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, HnswConfigDiff
import re
import asyncio
import requests
import time
import logging
from typing import Optional, Dict, Any, List

from src.services.qdrant_service import QdrantService
from src.services.document_service import DocumentService
from src.services.api_service import APIService
from src.logging_config import setup_logging

# Set up logging
setup_logging()

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
    qdrant_url = config.get_qdrant_url()
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to Qdrant at: {qdrant_url} (Attempt {attempt + 1}/{max_retries})")
            client = QdrantClient(
                url=qdrant_url,
                port=config.qdrant_http_port,
                timeout=30.0,
                prefer_grpc=False,  # Use HTTP in App Runner
                verify=config.qdrant_verify_ssl  # Use SSL verification based on config
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
    """Main Streamlit application class."""
    
    def __init__(self):
        """Initialize the Streamlit application."""
        # Set page config first
        st.set_page_config(
            page_title="RAG Application",
            page_icon="📚",
            layout="wide"
        )
        
        # Configure server headers for WebSocket support
        if hasattr(st, '_server'):
            st._server.add_header(
                "Content-Security-Policy",
                "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: ws: wss:; "
                "connect-src 'self' ws: wss: http: https: data: *; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: https:; "
                "style-src 'self' 'unsafe-inline' https:; "
                "img-src 'self' data: https:; "
                "frame-src 'self' https:;"
            )
            st._server.add_header(
                "Access-Control-Allow-Origin",
                "*"
            )
            st._server.add_header(
                "Access-Control-Allow-Methods",
                "GET, POST, OPTIONS"
            )
            st._server.add_header(
                "Access-Control-Allow-Headers",
                "DNT,X-CustomHeader,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Authorization"
            )
            st._server.add_header(
                "X-Frame-Options",
                "SAMEORIGIN"
            )
        
        # Initialize services
        self.qdrant_service = QdrantService()
        self.document_service = DocumentService()
        self.api_service = APIService()
        
        # Initialize session state
        self._init_session_state()
        
        # Initialize Qdrant connection (lazy loading)
        self.qdrant_connected = False
        
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temporary directory: {self.temp_dir}")
        
    def _init_session_state(self):
        """Initialize session state variables."""
        if 'documents' not in st.session_state:
            st.session_state.documents = []
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        if 'current_document' not in st.session_state:
            st.session_state.current_document = None
        if 'processed_documents' not in st.session_state:
            st.session_state.processed_documents = {}
        if 'api_authenticated' not in st.session_state:
            st.session_state.api_authenticated = False
        if 'api_password' not in st.session_state:
            st.session_state.api_password = ""
        if 'query_running' not in st.session_state:
            st.session_state.query_running = False
        if 'current_response' not in st.session_state:
            st.session_state.current_response = None
            
    def _ensure_qdrant_connection(self) -> bool:
        """Ensure Qdrant is connected before performing operations.
        
        Returns:
            bool: True if connected, False otherwise
        """
        if not self.qdrant_connected:
            self.qdrant_connected = self.qdrant_service.connect()
            if not self.qdrant_connected:
                st.error("Failed to connect to Qdrant. Please check your connection settings.")
                return False
        return True
    
    def _render_api_key_management(self):
        """Render the API key management interface."""
        with st.sidebar:
            st.title("API Configuration")
            
            # Check if API key is already saved
            if self.api_service.has_saved_key():
                if not st.session_state.api_authenticated:
                    # Show login form
                    password = st.text_input("Enter Password", type="password")
                    if st.button("Login"):
                        api_key = self.api_service.load_api_key(password)
                        if api_key:
                            st.session_state.api_authenticated = True
                            st.session_state.api_password = password
                            st.success("Successfully logged in!")
                        else:
                            st.error("Invalid password")
                else:
                    # Show API key management
                    st.success("✅ API Key Configured")
                    if st.button("Change API Key"):
                        st.session_state.api_authenticated = False
                        st.experimental_rerun()
            else:
                # Show API key setup form
                st.info("Please configure your API key")
                api_key = st.text_input("Enter API Key", type="password")
                password = st.text_input("Set Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                
                if st.button("Save API Key"):
                    if not api_key:
                        st.error("Please enter an API key")
                    elif not password:
                        st.error("Please enter a password")
                    elif password != confirm_password:
                        st.error("Passwords do not match")
                    else:
                        if self.api_service.save_api_key(api_key, password):
                            st.session_state.api_authenticated = True
                            st.session_state.api_password = password
                            st.success("API key saved successfully!")
                        else:
                            st.error("Failed to save API key")
    
    def render_sidebar(self):
        """Render the sidebar with document upload and management."""
        with st.sidebar:
            # API key management
            self._render_api_key_management()
            
            if st.session_state.api_authenticated:
                st.title("Document Management")
                
                # Document upload
                uploaded_file = st.file_uploader("Upload Document", type=['txt'])
                if uploaded_file:
                    self._handle_document_upload(uploaded_file)
                
                # Document list
                if st.session_state.documents:
                    st.subheader("Uploaded Documents")
                    for doc in st.session_state.documents:
                        if st.button(f"Select: {doc['name']}", key=f"select_{doc['name']}"):
                            st.session_state.current_document = doc
                            st.experimental_rerun()
    
    def _handle_document_upload(self, uploaded_file):
        """Handle document upload and processing.
        
        Args:
            uploaded_file: Streamlit UploadedFile object
        """
        try:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            # Process document
            processed_doc = self.document_service.process_document(tmp_path)
            if processed_doc:
                # Save processed document
                output_dir = os.path.join('data', 'processed')
                saved_path = self.document_service.save_processed_document(processed_doc, output_dir)
                
                if saved_path:
                    # Add to session state
                    st.session_state.documents.append({
                        'name': uploaded_file.name,
                        'path': saved_path,
                        'processed': processed_doc
                    })
                    st.success(f"Successfully processed {uploaded_file.name}")
                else:
                    st.error("Failed to save processed document")
            else:
                st.error("Failed to process document")
                
        except Exception as e:
            logger.error(f"Error handling document upload: {str(e)}")
            st.error("An error occurred while processing the document")
        finally:
            # Clean up temporary file
            if 'tmp_path' in locals():
                os.unlink(tmp_path)
    
    def render_main_content(self):
        """Render the main content area."""
        if not st.session_state.api_authenticated:
            st.warning("Please configure your API key in the sidebar to continue.")
            return
            
        st.title("RAG Application")
        
        # Document selection message
        if not st.session_state.current_document:
            st.info("Please select a document from the sidebar to begin.")
            return
            
        # Display current document info
        doc = st.session_state.current_document
        st.subheader(f"Current Document: {doc['name']}")
        
        # Document visualization
        self._render_document_visualization(doc['processed'])
        
        # Chat interface
        self._render_chat_interface(doc)
    
    def _render_document_visualization(self, processed_doc: Dict[str, Any]):
        """Render document visualization.
        
        Args:
            processed_doc: Processed document dictionary
        """
        with st.expander("Document Visualization", expanded=True):
            # Display metadata
            st.json(processed_doc['metadata'])
            
            # Display chunks
            st.subheader("Document Chunks")
            for i, chunk in enumerate(processed_doc['chunks']):
                with st.expander(f"Chunk {i+1}", expanded=False):
                    st.text_area("", chunk, height=200, disabled=True)
    
    def _render_chat_interface(self, doc: Dict[str, Any]):
        """Render the chat interface.
        
        Args:
            doc: Current document dictionary
        """
        st.subheader("Chat Interface")
        
        # Display chat history
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.text_area("", message["content"], height=200, disabled=True)
        
        # Chat input
        if prompt := st.chat_input("Ask a question about the document"):
            # Add user message to chat history
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            # Display user message
            with st.chat_message("user"):
                st.text_area("", prompt, height=200, disabled=True)
            
            # Process query
            if self._ensure_qdrant_connection():
                # Generate query embedding
                query_embedding = self.document_service._generate_embeddings([prompt])[0]
                
                # Search for similar chunks
                results = self.qdrant_service.search_similar(
                    collection_name=doc['name'],
                    query_vector=query_embedding
                )
                
                if results:
                    # Prepare response
                    response = self._prepare_response(results, prompt)
                    
                    # Add assistant message to chat history
                    st.session_state.chat_history.append({"role": "assistant", "content": response})
                    
                    # Display assistant message
                    with st.chat_message("assistant"):
                        st.text_area("", response, height=200, disabled=True)
                else:
                    st.warning("No relevant information found in the document.")
    
    def _prepare_response(self, results: List[Dict[str, Any]], query: str) -> str:
        """Prepare response from search results.
        
        Args:
            results: List of search results
            query: User query
            
        Returns:
            Formatted response string
        """
        # Extract relevant chunks
        chunks = [result['payload']['text'] for result in results]
        
        # Combine chunks into response
        response = "Based on the document content:\n\n"
        for i, chunk in enumerate(chunks, 1):
            response += f"{i}. {chunk}\n\n"
        
        return response
    
    async def process_query(self, query: str, is_doc_query: bool = False, split_content: str = None):
        """Process a query with streaming response and save history"""
        try:
            # Initialize tokenizer
            from transformers import BertTokenizer
            tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
            
            # Prepare messages based on query type
            if is_doc_query:
                if split_content:  # For split analysis queries
                    # Count tokens but don't enforce BERT's limit
                    token_count = len(tokenizer.encode(split_content, add_special_tokens=False))
                    logger.info(f"Split content token count: {token_count}")
                    
                    messages = [
                        {"role": "system", "content": "You are a helpful assistant analyzing a specific section of a document."},
                        {"role": "user", "content": f"Document section content: {split_content}\n\nQuestion: {query}"}
                    ]
                    max_tokens = 4096
                else:  # For full document queries
                    # Count tokens but don't enforce BERT's limit
                    token_count = len(tokenizer.encode(st.session_state.doc_content, add_special_tokens=False))
                    logger.info(f"Full document token count: {token_count}")
                    
                    messages = [
                        {"role": "system", "content": "You are a helpful assistant analyzing documents."},
                        {"role": "user", "content": f"Document content: {st.session_state.doc_content}\n\nQuestion: {query}"}
                    ]
                    max_tokens = 8192
            else:  # For general queries
                messages = [
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": query}
                ]
                max_tokens = 512

            # Create placeholder for streaming output
            response_container = st.empty()
            full_response = ""

            # Initialize session state for responses if not exists
            if 'current_response' not in st.session_state:
                st.session_state.current_response = None

            # Log the content being sent
            if split_content:
                logger.info(f"Processing split content of length: {len(split_content)} chars")
                logger.info(f"Token count for split: {len(tokenizer.encode(split_content))}")

            # Stream the response
            async for content in create_streaming_chat_completion(messages, max_tokens=max_tokens):
                if content:
                    full_response += content
                    response_container.markdown(full_response + "▌")
                    st.session_state.current_response = full_response

            # Final update without cursor
            if full_response:
                response_container.markdown(full_response)
                st.session_state.current_response = full_response
                
                # Save chat history
                self.save_chat_history(query, full_response, datetime.now().isoformat(), is_doc_query)
                
                return full_response
            else:
                error_msg = "No response received from the API"
                st.error(error_msg)
                logger.error(error_msg)
                return None

        except Exception as e:
            st.error(f"Error processing query: {str(e)}")
            logger.error(f"Error processing query: {str(e)}")
            return None
    
    def run(self):
        """Run the Streamlit application."""
        try:
            # Render sidebar
            self.render_sidebar()
            
            # Render main content
            self.render_main_content()
            
        except Exception as e:
            logger.error(f"Error running application: {str(e)}")
            st.error("An error occurred while running the application.")

def main():
    """Main entry point for the application"""
    # Initialize session state variable
    if 'trigger_rerun' not in st.session_state:
        st.session_state['trigger_rerun'] = False

    if st.session_state['trigger_rerun']:
        st.session_state['trigger_rerun'] = False
        st.rerun()  # Use this to trigger a rerun

    try:
        app = StreamlitApp()
        app.run()
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        st.error("An error occurred while running the application. Please check the logs for details.")

if __name__ == "__main__":
    main() 