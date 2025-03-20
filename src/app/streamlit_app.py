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

from ..document_processor import DocumentProcessor
from ..utils import create_streaming_chat_completion, validate_sambanova_setup
from ..vector_store import VectorStore

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
        st.write("Please enter your SambaNova API key to continue")
        
        api_key = st.text_input("SambaNova API Key", type="password")
        if st.button("Login"):
            if validate_sambanova_setup(api_key):
                st.session_state.is_authenticated = True
                st.session_state.api_key = api_key
                st.rerun()
            else:
                st.error("Invalid API key or connection failed. Please try again.")
                
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
            
            # Document Processing Settings
            st.subheader("Document Settings")
            chunk_size = st.slider(
                "Chunk Size",
                min_value=100,
                max_value=2000,
                value=1000,
                step=100
            )
            
            chunk_overlap = st.slider(
                "Chunk Overlap",
                min_value=0,
                max_value=200,
                value=100,
                step=10
            )
            
            # Vector Store Settings
            st.subheader("Vector Store Settings")
            collection_name = st.text_input(
                "Collection Name",
                value="documents"
            )
            
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
                
                # Stream the response
                for response_chunk in create_streaming_chat_completion(
                    messages=st.session_state.messages,
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
            
    def render_document_interface(self):
        st.title("Document Analysis")
        
        # File upload
        uploaded_file = st.file_uploader(
            "Upload a document",
            type=["pdf", "txt", "doc", "docx", "json"],
            help="Upload a document to analyze (PDF, TXT, DOC, DOCX, or JSON)"
        )
        
        if uploaded_file:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name
                
            try:
                # Process document
                text = self.document_processor.extract_text(tmp_file_path)
                st.session_state.current_document = text
                
                # Display document info
                st.subheader("Document Information")
                st.write(f"File name: {uploaded_file.name}")
                st.write(f"File type: {uploaded_file.type}")
                st.write(f"File size: {uploaded_file.size / 1024:.2f} KB")
                
                # Process document into chunks
                chunks = self.vector_store.process_document(text)
                st.session_state.document_chunks = chunks
                
                # Display chunks
                st.subheader("Document Chunks")
                for i, chunk in enumerate(chunks):
                    with st.expander(f"Chunk {i+1}"):
                        st.text(chunk)
                        
                # Create visualization
                st.subheader("Document Visualization")
                fig = self.vector_store.create_interactive_graph(chunks)
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Error processing document: {str(e)}")
                logger.error(f"Error processing document: {str(e)}")
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file: {str(e)}")
                    
    def render_document_split_interface(self):
        st.title("Document Split Analysis")
        
        if not st.session_state.current_document:
            st.warning("Please upload a document in the Document Analysis tab first.")
            return
            
        # Display document splits
        st.subheader("Document Splits")
        for i, chunk in enumerate(st.session_state.document_chunks):
            with st.expander(f"Split {i+1}"):
                st.text(chunk)
                
                # Chat interface for each split
                if prompt := st.chat_input(f"Ask about Split {i+1}"):
                    with st.chat_message("user"):
                        st.markdown(prompt)
                        
                    with st.chat_message("assistant"):
                        message_placeholder = st.empty()
                        full_response = ""
                        
                        # Stream the response
                        for response_chunk in create_streaming_chat_completion(
                            messages=[
                                {"role": "system", "content": f"You are analyzing Split {i+1} of the document."},
                                {"role": "user", "content": prompt}
                            ],
                            model="llama-2-70b-chat",
                            temperature=0.7,
                            max_tokens=1000,
                            top_p=0.9,
                            stream=True
                        ):
                            full_response += response_chunk
                            message_placeholder.markdown(full_response + "▌")
                            
                        message_placeholder.markdown(full_response)
                        
    def run(self):
        if not st.session_state.is_authenticated:
            self.render_login()
        else:
            self.render_sidebar()
            
            # Create tabs for different interfaces
            tab1, tab2, tab3 = st.tabs(["Chat", "Document Analysis", "Document Split Analysis"])
            
            with tab1:
                self.render_chat_interface()
            with tab2:
                self.render_document_interface()
            with tab3:
                self.render_document_split_interface()
                
def main():
    app = StreamlitApp()
    app.run()
    
if __name__ == "__main__":
    main() 