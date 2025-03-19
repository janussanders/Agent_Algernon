from typing import Optional, List, Dict, Any
import numpy as np
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, HnswConfigDiff
import logging
from src.config import config

logger = logging.getLogger(__name__)

class QdrantService:
    """Service class for handling Qdrant operations."""
    
    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self.is_connected = False
        
    def connect(self, max_retries: int = 5, retry_delay: int = 5) -> bool:
        """Connect to Qdrant with retries.
        
        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        qdrant_url = config.get_qdrant_url()
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to Qdrant at: {qdrant_url} (Attempt {attempt + 1}/{max_retries})")
                self.client = QdrantClient(
                    url=qdrant_url,
                    port=config.qdrant_http_port,
                    timeout=30.0,
                    prefer_grpc=False,
                    verify=config.qdrant_verify_ssl
                )
                # Test the connection
                self.client.get_collections()
                self.is_connected = True
                logger.info("Successfully connected to Qdrant")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to connect to Qdrant: {str(e)}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to connect to Qdrant after {max_retries} attempts: {str(e)}")
                    self.is_connected = False
                    return False
        return False
    
    def store_vectors(self, collection_name: str, vectors: List[np.ndarray], chunks: List[str], 
                     document_name: str) -> bool:
        """Store vectors in Qdrant collection.
        
        Args:
            collection_name: Name of the collection
            vectors: List of vectors to store
            chunks: List of text chunks
            document_name: Name of the document
            
        Returns:
            bool: True if storage successful, False otherwise
        """
        if not self.is_connected:
            logger.error("Cannot store vectors: Not connected to Qdrant")
            return False
            
        try:
            # Create collection with vector configuration
            self.client.recreate_collection(
                collection_name=collection_name,
                vectors_config={
                    "vectors": {
                        "size": 768,
                        "distance": "Cosine"
                    }
                }
            )
            
            # Prepare points for storage
            points = []
            for i, (vector, chunk_text) in enumerate(zip(vectors, chunks)):
                points.append({
                    "id": i,
                    "vector": {
                        "vectors": vector.tolist()
                    },
                    "payload": {
                        "chunk_index": i,
                        "text": chunk_text,
                        "document_name": document_name,
                        "timestamp": datetime.now().isoformat()
                    }
                })
            
            # Upload points
            self.client.upsert(
                collection_name=collection_name,
                points=points
            )
            
            logger.info(f"Successfully stored {len(points)} vectors in collection {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store vectors: {str(e)}")
            return False
    
    def search_similar(self, collection_name: str, query_vector: np.ndarray, 
                      limit: int = 5) -> List[Dict[str, Any]]:
        """Search for similar vectors in the collection.
        
        Args:
            collection_name: Name of the collection
            query_vector: Query vector
            limit: Maximum number of results
            
        Returns:
            List of similar vectors with their payloads
        """
        if not self.is_connected:
            logger.error("Cannot search: Not connected to Qdrant")
            return []
            
        try:
            results = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector.tolist(),
                limit=limit
            )
            return results
        except Exception as e:
            logger.error(f"Failed to search vectors: {str(e)}")
            return []
    
    def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Collection information or None if not found
        """
        if not self.is_connected:
            logger.error("Cannot get collection info: Not connected to Qdrant")
            return None
            
        try:
            return self.client.get_collection(collection_name)
        except Exception as e:
            logger.error(f"Failed to get collection info: {str(e)}")
            return None 