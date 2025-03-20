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
        """Initialize the Streamlit app"""
        st.set_page_config(
            page_title="Algernon",
            layout="wide",
            initial_sidebar_state="expanded"
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

        # Connect to Qdrant with retries
        try:
            self.qdrant_client = connect_to_qdrant()
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {str(e)}")
            self.qdrant_client = None

        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temporary directory: {self.temp_dir}")
        
        # Initialize document processor and vector store
        self.document_processor = DocumentProcessor()
        self.vector_store = VectorStore()
        
        # Initialize session state
        self.setup_session_state()
        
    def setup_session_state(self):
        """Initialize session state variables"""
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
        if 'doc_content' not in st.session_state:
            st.session_state.doc_content = None
        if 'doc_name' not in st.session_state:
            st.session_state.doc_name = None
        if 'api_validated' not in st.session_state:
            st.session_state.api_validated = False
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        if 'chat_responses' not in st.session_state:
            st.session_state.chat_responses = []
        if 'saved_responses' not in st.session_state:
            st.session_state.saved_responses = []
        if 'total_tokens' not in st.session_state:
            st.session_state.total_tokens = 0
        if 'embedding_fig' not in st.session_state:
            st.session_state.embedding_fig = None
        
    def render_login(self):
        """Render the login interface"""
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
        """Render the chat interface"""
        st.write("### Chat Interface")
        
        # Initialize saved responses in session state if not exists
        if 'saved_responses' not in st.session_state:
            st.session_state.saved_responses = self.load_saved_responses()
        
        # Chat input and processing
        query = st.text_input("Enter your query:", key="chat_input")
        if st.button("Send", key="send_button"):
            if query:
                # Initialize query state
                if 'chat_query_running' not in st.session_state:
                    st.session_state.chat_query_running = False
                
                if not st.session_state.chat_query_running:
                    try:
                        st.session_state.chat_query_running = True
                        # Run async query in a new event loop
                        response = asyncio.run(self.process_query(query, is_doc_query=False))
                        if response:
                            st.session_state.current_response = response
                    finally:
                        st.session_state.chat_query_running = False
            else:
                st.warning("Please enter a query")

    def render_document_chat(self):
        """Render the document chat interface"""
        st.write("### Document Analysis")
        
        # Document upload section
        uploaded_file = st.file_uploader(
            "Upload a document to analyze",
            type=["pdf", "json"],
            help="Upload a document to analyze"
        )
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if uploaded_file:
                if st.session_state.doc_name != uploaded_file.name:
                    with st.spinner("Processing document..."):
                        if self.process_uploaded_file(uploaded_file):
                            st.success(f"Successfully processed: {uploaded_file.name}")
                            st.session_state.doc_name = uploaded_file.name
                            logger.info(f"Document content length: {len(st.session_state.doc_content)}")
                        else:
                            st.error("Failed to process document")
        
        with col2:
            # Visualization toggle
            if uploaded_file and st.button("Generate Visualization"):
                with st.spinner("Creating document visualization..."):
                    try:
                        chunks, _ = self.vector_store.process_document(st.session_state.doc_content)
                        st.session_state.embedding_fig = self.vector_store.create_interactive_graph()
                        st.success("Visualization created!")
                    except Exception as e:
                        st.error(f"Failed to create visualization: {str(e)}")

    def render_token_analysis(self):
        """Render the document split analysis interface"""
        st.write("### Document Split Analysis")
        
        if not st.session_state.doc_content:
            st.info("Please upload a document in the Document Analysis tab first")
            return
        
        try:
            from transformers import BertTokenizer
            tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
            total_tokens = st.session_state.total_tokens
            
            # Add max token size input
            max_chunk_size = st.number_input(
                "Max Tokens per Split",
                min_value=1000,
                max_value=28000,
                value=16384,
                step=1000,
                help="Specify the maximum number of tokens per document split"
            )
            
            # Create document splits
            splits = self.create_document_splits(st.session_state.doc_content, tokenizer, max_chunk_size)
            
            # Display analysis
            num_splits = len(splits)
            st.markdown(f"""
            ### Document Analysis
            - Total Tokens: **{total_tokens:,}**
            - Max Tokens per Split: **{max_chunk_size:,}**
            - Number of Splits: **{num_splits}**
            """)
        except Exception as e:
            st.error(f"Error rendering token analysis: {str(e)}")

    def render(self):
        """Main render method for the Streamlit app"""
        if not st.session_state.is_authenticated:
            self.render_login()
            return
        
        # Render sidebar first
        self.render_sidebar()
        
        # Only show main content if API is validated
        if st.session_state.api_validated:
            # Main content area with tabs
            tab1, tab2, tab3 = st.tabs(["General Chat", "📄 Document Analysis", "🔢 Document Split Analysis"])
            
            with tab1:
                self.render_chat_interface()
                
            with tab2:
                self.render_document_chat()
                
            with tab3:
                self.render_token_analysis()
        else:
            st.warning("Please configure and validate your API credentials in the sidebar")

    def initialize_app(self):
        """Initialize the application and check API credentials"""
        with st.sidebar:
            st.write("### API Configuration")
            
            # API Key input
            api_key = st.text_input(
                "SambaNova API Key",
                value=st.session_state.api_key,
                type="password",
                key="api_key_input"
            )
            
            # API URL input
            api_url = st.text_input(
                "SambaNova API URL",
                value=os.getenv("SAMBANOVA_URL", "https://api.sambanova.ai/v1/chat/completions"),
                key="api_url_input"
            )
            
            # Model selection
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
            selected_model = st.selectbox(
                "Model",
                options=model_options,
                index=model_options.index(st.session_state.selected_model),
                key="model_selector"
            )
            st.session_state.selected_model = selected_model
            
            # Save button
            if st.button("Login"):
                if api_key and api_url:
                    try:
                        # Validate the setup
                        if validate_sambanova_setup(api_key):
                            st.session_state.api_validated = True
                            st.success("✅ API connection validated!")
                        else:
                            st.error("❌ API validation failed")
                    except Exception as e:
                        st.error(f"❌ API validation failed: {str(e)}")
                else:
                    st.warning("Please enter both API key and URL")

    def process_uploaded_file(self, uploaded_file):
        """Process an uploaded file and store its content"""
        try:
            if uploaded_file is None:
                return False
            
            # Save uploaded file
            file_path = os.path.join(self.temp_dir, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            logger.info(f"Saved file to: {file_path}")
            
            # Process the document content
            content = self.document_processor.extract_text(file_path)
            
            # Calculate total tokens
            from transformers import BertTokenizer
            tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
            total_tokens = len(tokenizer.encode(content, add_special_tokens=False))
            
            # Store in session state
            st.session_state.doc_content = content
            st.session_state.total_tokens = total_tokens
            logger.info(f"Processed document content: {len(content)} characters, {total_tokens} tokens")
            
            return True
            
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            logger.error(f"File processing error: {str(e)}")
            return False

def main():
    """Main entry point for the application"""
    # Initialize session state variable
    if 'trigger_rerun' not in st.session_state:
        st.session_state['trigger_rerun'] = False

    if st.session_state['trigger_rerun']:
        st.session_state['trigger_rerun'] = False
        st.rerun()  # Use this to trigger a rerun

    app = StreamlitApp()
    app.render()  # Use render() instead of run()

if __name__ == "__main__":
    main() 