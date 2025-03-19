import os
import tempfile
from pathlib import Path
from loguru import logger
import streamlit as st
from src.document_processor import DocumentProcessor
from src.utils import create_streaming_chat_completion, validate_sambanova_setup
from src.vector_store import VectorStore
import datetime
import json
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, HnswConfigDiff

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

class StreamlitApp:
    def __init__(self):
        st.set_page_config(page_title="Algernon", layout="wide")
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
            st.session_state.sambanova_url = os.getenv("SAMBANOVA_URL", "https://api.sambanova.ai/v1")
            
    def render_document_chat(self):
        """Render the document chat interface"""
        st.write("### Document Analysis")
        
        # Document upload section
        uploaded_file = st.file_uploader(
            "Upload a document",
            type=["txt", "pdf", "doc", "docx", "json"],
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
                                        "timestamp": datetime.datetime.now().isoformat()
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
                        timestamp = datetime.datetime.now()
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
                    self.process_query(doc_query, is_doc_query=True)
                else:
                    st.warning("Please enter a query about the document")
        else:
            st.info("Please upload a document to start asking questions about it")
    
    def process_query(self, query: str, is_doc_query: bool = False):
        """Process a query with streaming response"""
        try:
            # Prepare messages based on query type
            if is_doc_query and st.session_state.doc_content:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant analyzing documents. "
                                                "Use the provided document content to answer questions accurately. "
                                                "If the answer cannot be found in the document, please say so."},
                    {"role": "user", "content": f"Document content: {st.session_state.doc_content}\n\n"
                                              f"Question about the document: {query}"}
                ]
            else:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": query}
                ]
            
            # Create placeholder for streaming output
            response_container = st.empty()
            stats_container = st.empty()
            full_response = ""
            
            # Stream the response
            for chunk in create_streaming_chat_completion(messages):
                if isinstance(chunk, dict) and 'id' in chunk:
                    st.session_state.last_response_id = chunk['id']
                elif isinstance(chunk, str):
                    full_response += chunk
                    response_container.markdown(full_response + "▌")
            
            # Final update without cursor
            response_container.markdown(full_response)
            
        except Exception as e:
            st.error(f"Error processing query: {str(e)}")
            logger.error(f"Query processing error: {str(e)}")
    
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
            
            # Calculate total tokens when document is loaded
            from transformers import BertTokenizer
            tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
            total_tokens = len(tokenizer.encode(content))
            
            # Store in session state
            st.session_state.doc_content = content
            st.session_state.total_tokens = total_tokens
            logger.info(f"Processed document content: {len(content)} characters, {total_tokens} tokens")
            
            return True
            
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            logger.error(f"File processing error: {str(e)}")
            return False
    
    def render_sidebar(self):
        """Render the sidebar with status information"""
        with st.sidebar:
            st.write("### System Status")
            if check_qdrant():
                st.success("✅ Qdrant Connected")
            else:
                st.error("❌ Qdrant Connection Failed")
            
            st.write("### API Configuration")
            st.text("Endpoint:")
            st.code(os.getenv("SAMBANOVA_URL", "Not configured"))
            
            if hasattr(st.session_state, 'last_response_id'):
                st.text("Last Response ID:")
                st.code(st.session_state.last_response_id)
    
    def initialize_app(self):
        """Initialize the application and check API credentials"""
        with st.sidebar:
            st.write("### API Configuration")
            
            # API Key input
            api_key = st.text_input(
                "SambaNova API Key",
                value=st.session_state.sambanova_api_key,
                type="password",
                key="api_key_input"
            )
            
            # API URL input
            api_url = st.text_input(
                "SambaNova API URL",
                value=st.session_state.sambanova_url,
                key="api_url_input"
            )
            
            # Save button
            if st.button("Login"):
                if api_key and api_url:
                    # Update session state
                    st.session_state.sambanova_api_key = api_key
                    st.session_state.sambanova_url = api_url
                    
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
    
    def validate_api_key(self, api_key):
        """Validate the SambaNova API key"""
        try:
            from src.utils import validate_sambanova_setup
            validate_sambanova_setup()
        except Exception as e:
            raise ValueError(f"Failed to validate SambaNova setup: {str(e)}")

    def render(self):
        """Main render method for the Streamlit app"""
        st.title("Algernon")
        
        # Initialize API configuration
        self.initialize_app()
        
        # Only show main content if API is validated
        if st.session_state.api_validated:
            # Main content area with tabs
            tab1, tab2, tab3 = st.tabs(["💬 General Chat", "📄 Document Analysis", "🔢 Document Split Analysis"])
            
            with tab1:
                self.render_general_chat()
                
            with tab2:
                self.render_document_chat()
                
            with tab3:
                self.render_token_analysis()
        else:
            st.warning("Please configure and validate your API credentials in the sidebar")

    def render_general_chat(self):
        """Render the general chat interface"""
        st.write("### General Chat")
        query = st.text_area("Ask anything:", key="general_chat", height=100)
        
        if st.button("Send", key="general_send"):
            if query:
                self.process_query(query, is_doc_query=False)
            else:
                st.warning("Please enter a query")

    def render_token_analysis(self):
        """Render the Document Split Analysis interface"""
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
                max_value=100000,
                value=16384,
                step=1000,
                help="Specify the maximum number of tokens per document split"
            )
            
            # Calculate splits based on actual token counts, not character estimates
            doc_content = st.session_state.doc_content
            splits = []
            current_position = 0
            
            while current_position < len(doc_content):
                # Find a chunk that fits within token limit
                chunk_size = 1000  # Start with small chunk and grow
                current_chunk = doc_content[current_position:current_position + chunk_size]
                current_tokens = len(tokenizer.encode(current_chunk))
                
                # Binary search for optimal chunk size
                min_size = 0
                max_size = len(doc_content) - current_position
                
                while min_size < max_size:
                    mid_size = (min_size + max_size + 1) // 2
                    test_chunk = doc_content[current_position:current_position + mid_size]
                    tokens = len(tokenizer.encode(test_chunk))
                    
                    if tokens <= max_chunk_size:
                        min_size = mid_size
                        chunk_size = mid_size
                        current_chunk = test_chunk
                        current_tokens = tokens
                    else:
                        max_size = mid_size - 1
                
                # Find natural break point
                if current_position + chunk_size < len(doc_content):
                    break_chars = ["\n\n", "\n", ". ", " "]
                    for break_char in break_chars:
                        natural_break = current_chunk.rfind(break_char)
                        if natural_break != -1:
                            chunk_size = natural_break + len(break_char)
                            current_chunk = doc_content[current_position:current_position + chunk_size]
                            current_tokens = len(tokenizer.encode(current_chunk))
                            break
                
                splits.append({
                    "start": current_position,
                    "end": current_position + chunk_size,
                    "tokens": current_tokens,
                    "content": current_chunk
                })
                current_position += chunk_size
            
            # Display analysis
            num_splits = len(splits)
            st.markdown(f"""
            ### Document Analysis
            - Total Tokens: **{total_tokens:,}**
            - Max Tokens per Split: **{max_chunk_size:,}**
            - Number of Splits: **{num_splits}**
            """)
            
            st.markdown("### Document Splits")
            for i, split in enumerate(splits, 1):
                preview = split["content"][:100] + "..."
                split_content = split["content"]
                
                # Initialize session state for each split
                if f'vector_store_split_{i}' not in st.session_state:
                    st.session_state[f'vector_store_split_{i}'] = None
                if f'embedding_fig_split_{i}' not in st.session_state:
                    st.session_state[f'embedding_fig_split_{i}'] = None
                
                with st.expander(f"Split {i} of {num_splits}"):
                    st.text(preview)
                    st.markdown(f"""
                    - Characters: {len(split_content):,}
                    - Tokens: {split['tokens']:,}
                    - Percentage of Max Size: {(split['tokens'] / max_chunk_size) * 100:.1f}%
                    """)
                    
                    # Add save options in columns
                    save_col1, save_col2 = st.columns(2)
                    
                    with save_col1:
                        collection_name = st.text_input(
                            "Collection Name",
                            value=f"split_{i}_chunks",
                            key=f"collection_{i}",
                            help="Enter a name for the Qdrant collection"
                        )
                        
                        if st.button("Save to DB", key=f"qdrant_{i}"):
                            with st.spinner("Storing in Qdrant..."):
                                try:
                                    # Use or initialize vector store for this split
                                    if st.session_state[f'vector_store_split_{i}'] is None:
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
                                                "timestamp": datetime.datetime.now().isoformat()
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
                                if st.session_state[f'vector_store_split_{i}'] is None:
                                    st.session_state[f'vector_store_split_{i}'] = VectorStore()
                                    # Process only this split's content
                                    chunks, _ = st.session_state[f'vector_store_split_{i}'].process_document(split_content)
                                
                                vector_store = st.session_state[f'vector_store_split_{i}']
                                
                                timestamp = datetime.datetime.now()
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

def main():
    """Main entry point for the application"""
    app = StreamlitApp()
    app.render()

if __name__ == "__main__":
    main() 