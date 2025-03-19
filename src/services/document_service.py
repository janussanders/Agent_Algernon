from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime
import logging
from pathlib import Path
import tempfile
import os
from transformers import AutoTokenizer, AutoModel
import torch

logger = logging.getLogger(__name__)

class DocumentService:
    """Service class for handling document processing operations."""
    
    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
        self.model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
        self.chunk_size = 512
        self.chunk_overlap = 50
        
    def process_document(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Process a document and extract its content and metadata.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Dictionary containing document content and metadata, or None if processing fails
        """
        try:
            # Read document content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract metadata
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            created_at = datetime.fromtimestamp(os.path.getctime(file_path))
            
            # Split content into chunks
            chunks = self._split_into_chunks(content)
            
            # Generate embeddings for chunks
            embeddings = self._generate_embeddings(chunks)
            
            return {
                'content': content,
                'chunks': chunks,
                'embeddings': embeddings,
                'metadata': {
                    'file_name': file_name,
                    'file_size': file_size,
                    'created_at': created_at.isoformat(),
                    'num_chunks': len(chunks)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to process document {file_path}: {str(e)}")
            return None
    
    def _split_into_chunks(self, text: str) -> List[str]:
        """Split text into overlapping chunks.
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        tokens = self.tokenizer.encode(text)
        chunks = []
        start = 0
        
        while start < len(tokens):
            end = start + self.chunk_size
            chunk = tokens[start:end]
            chunks.append(self.tokenizer.decode(chunk))
            start = end - self.chunk_overlap
            
        return chunks
    
    def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            Numpy array of embeddings
        """
        embeddings = []
        
        for text in texts:
            inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True)
            with torch.no_grad():
                outputs = self.model(**inputs)
                embeddings.append(outputs.last_hidden_state.mean(dim=1).squeeze().numpy())
        
        return np.array(embeddings)
    
    def save_processed_document(self, document: Dict[str, Any], output_dir: str) -> Optional[str]:
        """Save processed document to disk.
        
        Args:
            document: Processed document dictionary
            output_dir: Directory to save the document
            
        Returns:
            Path to saved document or None if saving fails
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(output_dir, f"processed_{timestamp}.npz")
            
            # Save document data
            np.savez(
                output_file,
                content=document['content'],
                chunks=document['chunks'],
                embeddings=document['embeddings'],
                metadata=document['metadata']
            )
            
            logger.info(f"Successfully saved processed document to {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Failed to save processed document: {str(e)}")
            return None
    
    def load_processed_document(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Load a processed document from disk.
        
        Args:
            file_path: Path to the processed document file
            
        Returns:
            Dictionary containing document data or None if loading fails
        """
        try:
            data = np.load(file_path, allow_pickle=True)
            return {
                'content': data['content'].item(),
                'chunks': data['chunks'].tolist(),
                'embeddings': data['embeddings'],
                'metadata': data['metadata'].item()
            }
        except Exception as e:
            logger.error(f"Failed to load processed document {file_path}: {str(e)}")
            return None 