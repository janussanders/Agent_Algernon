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
        
        # Initialize session state
        if 'doc_content' not in st.session_state:
            st.session_state.doc_content = None
        if 'doc_name' not in st.session_state:
            st.session_state.doc_name = None
        if 'api_validated' not in st.session_state:
            st.session_state.api_validated = False
        if 'sambanova_api_key' not in st.session_state:
            st.session_state.sambanova_api_key = os.getenv("SAMBANOVA_API_KEY", "")
        if 'sambanova_url' not in st.session_state:
            st.session_state.sambanova_url = os.getenv(
                "SAMBANOVA_URL", 
                "https://api.sambanova.ai/v1/chat/completions"
            )
            
        # Add chat history to session state
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        if 'chat_responses' not in st.session_state:
            st.session_state.chat_responses = []
        
        self.load_saved_responses()

    def render(self):
        """Main render method for the Streamlit app"""
        st.title("Algernon")
        
        # Initialize API configuration
        self.initialize_app()
        
        # Only show main content if API is validated
        if st.session_state.api_validated:
            # Main content area with tabs
            tab1, tab2, tab3 = st.tabs([" General Chat", "📄 Document Analysis", "🔢 Document Split Analysis"])
            
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
        # Add custom CSS to hide password visibility toggle
        st.markdown("""
            <style>
            /* Hide the password visibility toggle */
            .stTextInput [data-testid="stTextInput"] > div > div > div > div > button {
                display: none !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        with st.sidebar:
            st.write("### API Configuration")
            
            # API Key input
            api_key = st.text_input(
                "SambaNova API Key",
                value=self.sambanova_api_key,
                type="password",
                key="api_key_input"
            )
            
            # API URL input
            api_url = st.text_input(
                "SambaNova API URL",
                value=self.sambanova_url,
                key="api_url_input"
            )
            
            # Add model selection dropdown
            if 'selected_model' not in st.session_state:
                st.session_state.selected_model = "DeepSeek-R1-Distill-Llama-70B"
            
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
                    # Update session state
                    self.sambanova_api_key = api_key
                    self.sambanova_url = api_url
                    
                    try:
                        # Validate the setup
                        validate_sambanova_setup()
                        st.session_state.api_validated = True
                        st.success("✅ API connection validated!")
                    except Exception as e:
                        st.session_state.api_validated = False
                        st.error(f"❌ API validation failed: {str(e)}")
                else:
                    st.warning("Please enter both API key and URL")

    def render_chat_interface(self):
        """Render the chat interface tab"""
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
        
        # Display chat history
        if 'chat_history' in st.session_state and st.session_state.chat_history:
            st.write("### Chat History")
            for idx, entry in enumerate(st.session_state.chat_history):
                with st.expander(f"💬 {entry['query'][:50]}... ({entry['timestamp'][:10]})"):
                    st.write(f"**Query:** {entry['query']}")
                    st.write(f"**Response:** {entry['response']}")
                    st.write(f"**Type:** {entry['type']}")

        # Display saved responses
        st.write("### Saved Vectors")
        if st.session_state.saved_responses:
            for idx, saved in enumerate(st.session_state.saved_responses):
                if isinstance(saved, dict):  # Ensure each entry is a dictionary
                    with st.expander(f"💬 {saved.get('query', '')[:50]}... ({saved.get('timestamp', '')[:10]})"):
                        st.write(f"**Query:** {saved.get('query', '')}")
                        st.write(f"**Response:** {saved.get('response', '')}")
                        st.write(f"**Model:** {saved.get('model', '')}")
                        
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            if st.button("🗑️ Delete", key=f"delete_{idx}"):
                                st.session_state.saved_responses.pop(idx)
                                self.save_response_to_file(st.session_state.saved_responses)  # Update file
                                st.session_state['trigger_rerun'] = True
                        with col2:
                            if st.button("💾 Store in Qdrant", key=f"store_{idx}"):
                                try:
                                    # Store in Qdrant
                                    vector_store = VectorStore()
                                    vector_store.store_chat_response(
                                        query=saved.get('query', ''),
                                        response=saved.get('response', ''),
                                        metadata={
                                            'timestamp': saved.get('timestamp', ''),
                                            'model': saved.get('model', ''),
                                            'response_id': saved.get('id', '')
                                        }
                                    )
                                    st.success("Stored in Qdrant!")
                                except Exception as e:
                                    st.error(f"Failed to store in Qdrant: {str(e)}")

    def render_document_chat(self):
        """Render the document chat interface"""
        st.write("### Document Analysis")
        
        # Document upload section
        uploaded_file = st.file_uploader(
            "Upload a document to analyze",
            type=["pdf","json"],
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
                        st.session_state.vector_store = VectorStore()
                        chunks, _ = st.session_state.vector_store.process_document(st.session_state.doc_content)
                        st.session_state.embedding_fig = st.session_state.vector_store.create_interactive_graph()
                        st.success("Visualization created!")
                    except Exception as e:
                        st.error(f"Failed to create visualization: {str(e)}")
        
        # Show visualization and storage options if they exist
        if hasattr(st.session_state, 'embedding_fig'):
            with st.expander("Document Visualization", expanded=False):
                st.plotly_chart(st.session_state.embedding_fig, use_container_width=True)
            
            # Storage options
            st.write("### Storage Options")
            store_col1, store_col2 = st.columns(2)
            
            with store_col1:
                # Add collection name input
                collection_name = st.text_input(
                    "Collection Name",
                    value="document_chunks",
                    help="Enter a name for the Qdrant collection or use default"
                )
                
                if st.button("Save to DB"):
                    with st.spinner("Configuring HNSW index..."):
                        try:
                            # First ensure we have processed the document
                            if not hasattr(st.session_state.vector_store, 'chunks') or not st.session_state.vector_store.chunks:
                                chunks, _ = st.session_state.vector_store.process_document(st.session_state.doc_content)
                            else:
                                chunks = st.session_state.vector_store.chunks
                            
                            # Create collection with correct vector configuration
                            st.session_state.vector_store.client.recreate_collection(
                                collection_name=collection_name,
                                vectors_config={
                                    "vectors": {
                                        "size": 768,
                                        "distance": "Cosine"
                                    }
                                }
                            )
                            
                            # Reconstruct full vectors from PQ codes
                            reconstructed_vectors = []
                            for pq_code in st.session_state.vector_store.pq_codes:
                                vector = np.zeros(768)  # Full BERT vector size
                                for i, (code, codebook) in enumerate(zip(pq_code, st.session_state.vector_store.codebooks)):
                                    start_idx = i * st.session_state.vector_store.segment_size
                                    end_idx = start_idx + st.session_state.vector_store.segment_size
                                    vector[start_idx:end_idx] = codebook.cluster_centers_[code]
                                reconstructed_vectors.append(vector)
                            
                            # Store vectors in the collection
                            points = []
                            for i, (vector, chunk_text) in enumerate(zip(reconstructed_vectors, chunks)):
                                points.append({
                                    "id": i,
                                    "vector": {
                                        "vectors": vector.tolist()  # Full 768-dim vector
                                    },
                                    "payload": {
                                        "chunk_index": i,
                                        "text": chunk_text,  # Include the chunk text
                                        "document_name": st.session_state.doc_name,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                })
                            
                            # Upload points to the collection
                            st.session_state.vector_store.client.upsert(
                                collection_name=collection_name,
                                points=points
                            )
                            
                            st.success("✅ Vectors stored in Qdrant")
                            with st.expander("Qdrant Collection Details"):
                                st.markdown(f"""
                                    ### Qdrant Dashboard Access
                                    - URL: `http://localhost:6333/dashboard`
                                    - Collection Name: `{collection_name}`
                                    - Vector Count: {len(points)}
                                    
                                    ### Collection Configuration
                                    - Vector Size: 768 (BERT)
                                    - Distance: Cosine
                                    - Index: HNSW
                                    """)
                        except Exception as e:
                            st.error("❌ Failed to store vectors")
                            logger.error(f"HNSW index creation error: {str(e)}")
            
            with store_col2:
                if st.button("Save as JSON"):
                    try:
                        timestamp = datetime.now()
                        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
                        default_filename = f"vectors_{st.session_state.doc_name}_{timestamp_str}.json"
                        
                        # Get chunks from vector store
                        chunks = st.session_state.vector_store.chunks if hasattr(st.session_state.vector_store, 'chunks') else []
                        
                        vector_data = {
                            "timestamp": timestamp.isoformat(),
                            "model_timestamp": "2019-05-31",  # BERT base uncased release
                            "document_name": st.session_state.doc_name,
                            "document_content": st.session_state.doc_content,
                            "chunks": chunks,  # Add actual chunks
                            "pq_codes": st.session_state.vector_store.pq_codes.tolist(),
                            "codebooks": [codebook.cluster_centers_.tolist() 
                                        for codebook in st.session_state.vector_store.codebooks],
                            "metadata": {
                                "n_segments": st.session_state.vector_store.n_segments,
                                "n_clusters": st.session_state.vector_store.n_clusters,
                                "segment_size": st.session_state.vector_store.segment_size,
                                "model_name": "bert-base-uncased",
                                "model_version": "v1",
                                "vector_size": 768,
                                "chunk_size": 512,
                                "overlap": 128,
                                "distance_metric": "cosine",
                                "quantization": "product_quantization",
                                "huggingface_model": "bert-base-uncased",
                                "model_details": {
                                    "architecture": "BERT",
                                    "release_date": "2019-05-31",
                                    "provider": "huggingface",
                                    "license": "Apache 2.0",
                                    "timestamps": {
                                        "model_release": "2019-05-31",
                                        "embedding_created": timestamp.isoformat(),
                                        "last_updated": "2019-05-31",
                                        "model_version": "v1.0"
                                    }
                                },
                                "chunking_details": {
                                    "total_chunks": len(chunks),
                                    "chunk_sizes": [len(chunk) for chunk in chunks] if chunks else [],
                                    "average_chunk_size": sum(len(chunk) for chunk in chunks)/len(chunks) if chunks else 0,
                                    "config": {
                                        "method": "sliding_window",
                                        "chunk_size": 512,
                                        "chunk_overlap": 128,
                                        "min_chunk_size": 100,
                                        "separators": ["\n\n", "\n", ". ", " ", ""],
                                        "length_function": "character_length",
                                        "clean_text": True
                                    }
                                }
                            }
                        }
                        
                        st.download_button(
                            "📥 Download Processed Vectors",
                            data=json.dumps(vector_data, cls=NumpyEncoder),
                            file_name=default_filename,
                            mime="application/json"
                        )
                        st.success("✅ Vector embeddings processed successfully")
                        
                        # Show metadata preview with chunking information
                        with st.expander("Metadata Preview"):
                            preview_data = {
                                "total_chunks": len(chunks),
                                "average_chunk_size": vector_data["metadata"]["chunking_details"]["average_chunk_size"],
                                "chunking_config": vector_data["metadata"]["chunking_details"]["config"]
                            }
                            st.json(preview_data)
                            
                    except Exception as e:
                        st.error(f"❌ Failed to process vectors: {str(e)}")
                        logger.error(f"Vector processing error: {str(e)}")
        
        # Document query section
        if st.session_state.doc_content:
            st.write(f"Current document: **{st.session_state.doc_name}**")
            
            # Document content preview
            with st.expander("Document Preview", expanded=False):
                st.text(st.session_state.doc_content[:1000] + "..." if len(st.session_state.doc_content) > 1000 else st.session_state.doc_content)
            
            # Query input
            doc_query = st.text_area("Ask about the document:", key="doc_chat", height=100)
            
            if st.button("Ask", key="doc_send"):
                if doc_query:
                    # Initialize query state
                    if 'query_running' not in st.session_state:
                        st.session_state.query_running = False
                    
                    if not st.session_state.query_running:
                        try:
                            st.session_state.query_running = True
                            # Run async query in a new event loop
                            response = asyncio.run(self.process_query(doc_query, is_doc_query=True))
                            if response:
                                st.session_state.current_response = response
                        finally:
                            st.session_state.query_running = False
                else:
                    st.warning("Please enter a query about the document")
        else:
            st.info("Please upload a document to start asking questions about it")

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
                max_value=28000,  # Adjusted to match your context length requirement
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
            
            # Process each split
            for i, split in enumerate(splits, 1):
                preview = split["content"][:100] + "..."
                split_content = split["content"]
                
                with st.expander(f"Split {i} of {num_splits} - {split.get('section_title', '')}"):
                    st.text(preview)
                    st.markdown(f"""
                    - Characters: {len(split_content):,}
                    - Tokens: {split['tokens']:,}
                    - Percentage of Max Size: {(split['tokens'] / max_chunk_size) * 100:.1f}%
                    """)
                    
                    # Query input for each chunk
                    query = st.text_area(f"Query for Split {i}:", key=f"query_split_{i}", height=100)
                    
                    # Initialize response in session state if not exists
                    if f'query_response_split_{i}' not in st.session_state:
                        st.session_state[f'query_response_split_{i}'] = None
                    
                    if st.button(f"Send", key=f"send_query_split_{i}"):
                        if query:
                            # Initialize query state for this split
                            query_state_key = f'query_running_split_{i}'
                            if query_state_key not in st.session_state:
                                st.session_state[query_state_key] = False
                            
                            if not st.session_state[query_state_key]:
                                try:
                                    st.session_state[query_state_key] = True
                                    # Run async query in a new event loop
                                    response = asyncio.run(self.process_query(
                                        query, 
                                        is_doc_query=True, 
                                        split_content=split_content
                                    ))
                                    if response:
                                        st.session_state[f'query_response_split_{i}'] = response
                                finally:
                                    st.session_state[query_state_key] = False
                        else:
                            st.warning(f"Please enter a query for Split {i}")
                    
                    # Add save options in columns
                    save_col1, save_col2 = st.columns(2)
                    
                    with save_col1:
                        collection_name = st.text_input(
                            "Collection Name",
                            value=f"Document_split_{i}",
                            key=f"collection_{i}",
                            help="Enter a name for the Qdrant collection"
                        )
                        
                        if st.button("Save to DB", key=f"qdrant_{i}"):
                            with st.spinner("Storing in Qdrant..."):
                                try:
                                    # Use or initialize vector store for this split
                                    if st.session_state.get(f'vector_store_split_{i}') is None:
                                        st.session_state[f'vector_store_split_{i}'] = VectorStore()
                                        # Process only this split's content
                                        chunks, _ = st.session_state[f'vector_store_split_{i}'].process_document(split_content)
                                    
                                    vector_store = st.session_state[f'vector_store_split_{i}']
                                    
                                    # Create collection with correct vector configuration
                                    vector_store.client.recreate_collection(
                                        collection_name=collection_name,
                                        vectors_config={
                                            "vectors": {
                                                "size": 768,
                                                "distance": "Cosine"
                                            }
                                        }
                                    )
                                    
                                    # Store vectors in the collection
                                    points = []
                                    for j, (vector, chunk_text) in enumerate(zip(vector_store.pq_codes, vector_store.chunks)):
                                        points.append({
                                            "id": j,
                                            "vector": {
                                                "vectors": vector.tolist()
                                            },
                                            "payload": {
                                                "chunk_index": j,
                                                "text": chunk_text,
                                                "document_name": f"{st.session_state.doc_name}_split_{i}",
                                                "split_number": i,
                                                "total_splits": num_splits,
                                                "timestamp": datetime.now().isoformat()
                                            }
                                        })
                                    
                                    vector_store.client.upsert(
                                        collection_name=collection_name,
                                        points=points
                                    )
                                    st.success("✅ Vectors stored in Qdrant")
                                except Exception as e:
                                    st.error(f"❌ Failed to store vectors: {str(e)}")
                    
                    with save_col2:
                        if st.button("Save as JSON", key=f"json_{i}"):
                            try:
                                # Use or initialize vector store for this split
                                if st.session_state.get(f'vector_store_split_{i}') is None:
                                    st.session_state[f'vector_store_split_{i}'] = VectorStore()
                                    # Process only this split's content
                                    chunks, _ = st.session_state[f'vector_store_split_{i}'].process_document(split_content)
                                
                                vector_store = st.session_state[f'vector_store_split_{i}']
                                
                                timestamp = datetime.now()
                                output_file = f"data/vectors_split_{i}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
                                
                                with open(output_file, 'w') as f:
                                    json.dump({
                                        "schema_version": "1.0",
                                        "timestamp": timestamp.isoformat(),
                                        "split_info": {
                                            "split_number": i,
                                            "total_splits": num_splits,
                                            "token_count": split['tokens'],
                                            "max_token_size": max_chunk_size,
                                            "start_char": split["start"],
                                            "end_char": split["end"]
                                        },
                                        "document_name": f"{st.session_state.doc_name}_split_{i}",
                                        "document_content": split_content,
                                        "vectors": [v.tolist() for v in vector_store.pq_codes]
                                    }, f)
                                
                                st.success(f"✅ Saved to {output_file}")
                            except Exception as e:
                                st.error(f"❌ Failed to save JSON: {str(e)}")
                            
        except Exception as e:
            st.error(f"Error in document split analysis: {str(e)}")
            logger.error(f"Document split analysis error: {str(e)}")

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
            processor = DocumentProcessor()
            content = processor.extract_text(file_path)
            
            # Calculate total tokens in chunks to avoid token length errors
            from transformers import BertTokenizer
            tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
            
            # Process the content in chunks
            chunk_size = 450  # Leave room for special tokens
            total_tokens = 0
            start = 0
            text_len = len(content)
            
            while start < text_len:
                end = start + 1000  # Process 1000 characters at a time
                if end > text_len:
                    end = text_len
                
                chunk = content[start:end]
                total_tokens += len(tokenizer.encode(chunk, add_special_tokens=False))
                start = end
            
            # Store in session state
            st.session_state.doc_content = content
            st.session_state.total_tokens = total_tokens
            logger.info(f"Processed document content: {len(content)} characters, {total_tokens} tokens")
            
            return True
            
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            logger.error(f"File processing error: {str(e)}")
            return False

    def save_response_to_file(self, response, file_path='data/responses.json'):
        """Save response to a JSON file."""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Load existing responses
            if os.path.exists(file_path):
                with open(file_path, 'r') as file:
                    responses = json.load(file)
            else:
                responses = []

            # Append new response
            responses.append(response)

            # Save back to file
            with open(file_path, 'w') as file:
                json.dump(responses, file, indent=4)

            # Update session state
            st.session_state.saved_responses = responses

            logger.info("Response saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save response: {str(e)}")

    def load_saved_responses(self, file_path='data/responses.json'):
        """Load saved responses from a JSON file."""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as file:
                    responses = json.load(file)
                logger.info("Loaded saved responses successfully.")
                return responses
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to load saved responses: {str(e)}")
            return []

    def save_chat_history(self, query, full_response, timestamp, is_doc_query=False):
        """Add the chat response to the session state."""
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []

        # Create a chat entry
        chat_entry = {
            "query": query,
            "response": full_response,
            "timestamp": timestamp,
            "type": "document" if is_doc_query else "general"
        }

        # Check if the response is already in the chat history
        if not any(entry['query'] == query and entry['response'] == full_response for entry in st.session_state.chat_history):
            # Add the chat entry to the session state
            st.session_state.chat_history.append(chat_entry)
            logger.info("Chat entry added to session state.")
        else:
            logger.info("Duplicate chat entry detected, not adding to session state.")

    def find_optimal_chunk_size(self, text, tokenizer, max_tokens):
        """Binary search to find optimal chunk size that fits within token limit"""
        left, right = 0, len(text)
        optimal_size = 0
        
        while left <= right:
            mid = (left + right) // 2
            tokens = len(tokenizer.encode(text[:mid]))
            
            if tokens <= max_tokens:
                optimal_size = mid
                left = mid + 1
            else:
                right = mid - 1
        
        return optimal_size

    def find_natural_break(self, text, window=100):
        """Find natural break point near the end of text"""
        break_points = ['\n\n', '\n', '. ', ' ']
        search_start = max(0, len(text) - window)
        
        for separator in break_points:
            last_break = text[search_start:].rfind(separator)
            if last_break != -1:
                return search_start + last_break + len(separator)
        
        return len(text)

    def create_document_splits(self, content, tokenizer, max_tokens):
        """Create document splits with enhanced metadata"""
        try:
            splits = []
            current_position = 0
            
            while current_position < len(content):
                # Find optimal chunk size
                chunk_size = self.find_optimal_chunk_size(
                    content[current_position:],
                    tokenizer,
                    max_tokens
                )
                
                # Find natural break point
                chunk_end = self.find_natural_break(
                    content[current_position:current_position + chunk_size]
                )
                
                current_chunk = content[current_position:current_position + chunk_end]
                current_tokens = len(tokenizer.encode(current_chunk))
                
                # Extract section title if available
                section_title = self.extract_section_title(current_chunk)
                
                splits.append({
                    "start": current_position,
                    "end": current_position + chunk_end,
                    "tokens": current_tokens,
                    "content": current_chunk,
                    "section_title": section_title,
                    "token_density": current_tokens / len(current_chunk) if current_chunk else 0,
                    "timestamp": datetime.now().isoformat()
                })
                
                current_position += chunk_end
            
            return splits
            
        except Exception as e:
            logger.error(f"Error in create_document_splits: {str(e)}")
            return []

    def extract_section_title(self, chunk, max_length=50):
        """Extract potential section title from chunk"""
        try:
            # Look for common section title patterns
            patterns = [
                r'^#+\s*(.+)$',  # Markdown headers
                r'^[A-Z][A-Za-z\s]{2,}\:',  # Capitalized phrase followed by colon
                r'^\d+\.\s+([A-Z][A-Za-z\s]{2,})',  # Numbered sections
            ]
            
            lines = chunk.split('\n')
            for line in lines[:3]:  # Check first 3 lines
                line = line.strip()
                if not line:
                    continue
                
                for pattern in patterns:
                    match = re.match(pattern, line)
                    if match:
                        title = match.group(1) if match.groups() else line
                        return title[:max_length] + ('...' if len(title) > max_length else '')
            
            # Fallback: use first non-empty line
            for line in lines:
                if line.strip():
                    return line.strip()[:max_length] + ('...' if len(line.strip()) > max_length else '')
            
            return "Untitled Section"
            
        except Exception as e:
            logger.error(f"Error in extract_section_title: {str(e)}")
            return "Untitled Section"

def main():
    """Main entry point for the application"""
    # Initialize session state variable
    if 'trigger_rerun' not in st.session_state:
        st.session_state['trigger_rerun'] = False

    if st.session_state['trigger_rerun']:
        st.session_state['trigger_rerun'] = False
        st.rerun()  # Use this to trigger a rerun

    app = StreamlitApp()
    app.render()

if __name__ == "__main__":
    main() 