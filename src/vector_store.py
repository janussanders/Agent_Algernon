from transformers import BertTokenizer, BertModel
import torch
from typing import List, Dict, Tuple
import numpy as np
from loguru import logger
import os
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA
import plotly.graph_objects as go
import networkx as nx
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import euclidean_distances
import uuid

class VectorStore:
    def __init__(self, n_segments=4, n_clusters=32):
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        qdrant_https = os.getenv("QDRANT_HTTPS", "false").lower() == "true"
        qdrant_url = f"https://{qdrant_host}" if qdrant_https else f"http://{qdrant_host}"
        
        self.client = QdrantClient(
            url=qdrant_url,
            port=qdrant_port,
            timeout=30.0,
            prefer_grpc=False,  # Use HTTP in App Runner
            verify=False  # Skip SSL verification for internal VPC communication
        )
        # Initialize BERT
        self.tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
        self.model = BertModel.from_pretrained('bert-base-uncased')
        self.collection_name = "vector_embeddings"
        self._ensure_collection()
        self.n_segments = n_segments
        self.n_clusters = n_clusters
        self.segment_size = None
        self.codebooks = []
        self.pq_codes = []
        self.chunks = []
        
    def _ensure_collection(self):
        """Ensure collection exists with correct settings"""
        try:
            # Try to get collection, recreate if it doesn't exist
            try:
                self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted existing collection: {self.collection_name}")
            except Exception:
                pass
            
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=768,  # BERT base hidden size
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Created collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error ensuring collection: {str(e)}")
            raise

    def _create_chunks(self, text: str, chunk_size: int = 256, overlap: int = 64) -> List[str]:
        """Create overlapping chunks from text"""
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = start + chunk_size
            # Find the last period or newline before chunk_size
            if end < text_len:
                last_period = text.rfind('.', start, end)
                last_newline = text.rfind('\n', start, end)
                end = max(last_period, last_newline) if max(last_period, last_newline) > -1 else end
            
            chunk = text[start:end].strip()
            if chunk:  # Only add non-empty chunks
                chunks.append(chunk)
            start = end - overlap
            
        # Ensure we have enough chunks for meaningful visualization
        if len(chunks) < self.n_clusters:
            # Create smaller chunks if needed
            new_chunk_size = max(128, len(text) // (self.n_clusters + 1))
            return self._create_chunks(text, chunk_size=new_chunk_size, overlap=32)
            
        return chunks

    def process_document(self, content: str):
        """Process document content into chunks and vectors"""
        try:
            # Clear existing data
            self.chunks = []
            self.codebooks = []
            self.pq_codes = []
            
            # Chunk the document
            self.chunks = self._create_chunks(content)
            logger.info(f"Created {len(self.chunks)} chunks")
            
            # Create embeddings
            vectors = self._create_embeddings(self.chunks)
            logger.info(f"Created embeddings with shape: {vectors.shape}")
            
            # Store chunks and vectors in Qdrant
            points = []
            for i, (chunk, vector) in enumerate(zip(self.chunks, vectors)):
                points.append(models.PointStruct(
                    id=i,
                    vector=vector.tolist(),
                    payload={"text": chunk}
                ))
            
            if points:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
                logger.info(f"Stored {len(points)} points in Qdrant")
            
            return self.chunks, vectors
            
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            raise

    def _split_vector(self, vector: np.ndarray) -> List[np.ndarray]:
        """Split vector into M segments"""
        return np.array_split(vector, self.n_segments)
    
    def train_product_quantizer(self, vectors: np.ndarray):
        """Train Product Quantizer on the dataset"""
        n_vectors, dim = vectors.shape
        self.segment_size = dim // self.n_segments
        
        # Split vectors into segments
        segments = []
        for i in range(self.n_segments):
            start = i * self.segment_size
            end = start + self.segment_size if i < self.n_segments - 1 else dim
            segments.append(vectors[:, start:end])
        
        # Train k-means for each segment
        self.codebooks = []
        for segment_vectors in segments:
            kmeans = KMeans(n_clusters=self.n_clusters, random_state=42)
            kmeans.fit(segment_vectors)
            self.codebooks.append(kmeans)
            
    def encode_vectors(self, vectors: np.ndarray) -> np.ndarray:
        """Encode vectors using trained product quantizer"""
        n_vectors = len(vectors)
        codes = np.zeros((n_vectors, self.n_segments), dtype=np.int32)
        
        for m in range(self.n_segments):
            start = m * self.segment_size
            end = start + self.segment_size if m < self.n_segments - 1 else vectors.shape[1]
            segment_vectors = vectors[:, start:end]
            codes[:, m] = self.codebooks[m].predict(segment_vectors)
            
        return codes
    
    def compute_distance_table(self, query: np.ndarray) -> np.ndarray:
        """Compute distance table for query vector"""
        distance_table = np.zeros((self.n_segments, self.n_clusters))
        query_segments = self._split_vector(query)
        
        for m, (q_segment, codebook) in enumerate(zip(query_segments, self.codebooks)):
            distance_table[m] = euclidean_distances(
                q_segment.reshape(1, -1),
                codebook.cluster_centers_
            )[0]
            
        return distance_table
    
    def approximate_nearest_neighbor(self, query: np.ndarray, k: int = 5) -> List[Tuple[int, float]]:
        """Find approximate nearest neighbors using PQ"""
        distance_table = self.compute_distance_table(query)
        
        # Compute approximate distances
        distances = np.zeros(len(self.pq_codes))
        for i, code in enumerate(self.pq_codes):
            distances[i] = sum(distance_table[m, c] for m, c in enumerate(code))
            
        # Get top k nearest neighbors
        nearest_idx = np.argsort(distances)[:k]
        return [(idx, distances[idx]) for idx in nearest_idx]
    
    def get_word_embeddings(self, text: str) -> np.ndarray:
        """Get BERT embeddings for text"""
        inputs = self.tokenizer.encode_plus(
            text,
            add_special_tokens=True,
            max_length=512,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )
        
        with torch.no_grad():
            outputs = self.model(
                inputs['input_ids'],
                attention_mask=inputs['attention_mask']
            )
        
        # Get [CLS] token embedding
        embeddings = outputs.last_hidden_state[:, 0, :].numpy()
        return embeddings[0]  # Return as 1D array

    def _create_embeddings(self, chunks: List[str]) -> np.ndarray:
        """Create BERT embeddings for text chunks"""
        embeddings = []
        
        with torch.no_grad():
            for chunk in chunks:
                # Tokenize and encode the chunk
                inputs = self.tokenizer(
                    chunk,
                    return_tensors="pt",
                    max_length=512,
                    padding=True,
                    truncation=True
                )
                
                # Get BERT embeddings
                outputs = self.model(**inputs)
                
                # Use [CLS] token embedding as chunk embedding
                embedding = outputs.last_hidden_state[0, 0, :].numpy()
                embeddings.append(embedding)
        
        # Convert to numpy array
        embeddings_array = np.array(embeddings)
        
        # Train product quantizer if not already trained
        if not self.codebooks:
            self.train_product_quantizer(embeddings_array)
        
        # Encode vectors using product quantization
        self.pq_codes = self.encode_vectors(embeddings_array)
        
        return embeddings_array

    def store_chat_response(self, query: str, response: str, metadata: dict = None):
        """Store a chat response in the vector database"""
        try:
            # Ensure the collection exists
            self._ensure_chat_collection()

            # Create combined text for embedding
            combined_text = f"Query: {query}\nResponse: {response}"
            
            # Get embedding
            embedding = self.get_embedding(combined_text)
            
            # Prepare point for storage
            point = {
                "id": str(uuid.uuid4()),
                "vector": embedding.tolist(),
                "payload": {
                    "query": query,
                    "response": response,
                    "type": "chat_response",
                    **metadata
                }
            }
            
            # Store in Qdrant
            self.client.upsert(
                collection_name="chat_responses",
                points=[point]
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store chat response: {str(e)}")
            raise

    def _ensure_chat_collection(self):
        """Ensure the chat_responses collection exists"""
        try:
            self.client.create_collection(
                collection_name="chat_responses",
                vectors_config=VectorParams(
                    size=768,  # Assuming BERT base hidden size
                    distance=Distance.COSINE
                )
            )
            logger.info("Created chat_responses collection.")
        except Exception as e:
            if "already exists" not in str(e):
                logger.error(f"Error ensuring chat_responses collection: {str(e)}")
                raise

    def get_embedding(self, text):
        """Get BERT embedding for a text"""
        # Tokenize and prepare for model
        inputs = self.tokenizer(
            text, 
            return_tensors="pt", 
            max_length=512, 
            truncation=True, 
            padding=True
        )
        
        # Get model output
        with torch.no_grad():
            outputs = self.model(**inputs)
            
        # Use CLS token embedding as text representation
        embedding = outputs.last_hidden_state[0, 0, :].numpy()
        return embedding

    def create_interactive_graph(self) -> go.Figure:
        """Create visualization using PQ-encoded vectors"""
        try:
            points = self.client.scroll(
                collection_name=self.collection_name,
                limit=1000
            )[0]
            
            if not points:
                return self._create_fallback_visualization()
            
            # Get unique centroids from each segment
            centroids_3d = []
            chunk_texts = {}  # Store texts for each cluster
            
            for m, codebook in enumerate(self.codebooks):
                centers = codebook.cluster_centers_
                pca = PCA(n_components=3)
                segment_centroids = pca.fit_transform(centers)
                centroids_3d.extend(segment_centroids)
                
                # Group texts by cluster
                for i, code in enumerate(self.pq_codes[:, m]):
                    cluster_key = f"{m}_{code}"
                    if cluster_key not in chunk_texts:
                        chunk_texts[cluster_key] = []
                    if i < len(points):
                        chunk_texts[cluster_key].append(points[i].payload["text"])
            
            centroids_3d = np.array(centroids_3d)
            
            # Create graph
            G = nx.Graph()
            
            # Add nodes for each significant centroid
            for i, pos in enumerate(centroids_3d):
                segment = i // self.n_clusters
                cluster = i % self.n_clusters
                cluster_key = f"{segment}_{cluster}"
                
                # Count vectors using this centroid
                usage_count = np.sum(self.pq_codes[:, segment] == cluster)
                
                if usage_count > 0:
                    # Get sample texts for this cluster
                    cluster_samples = chunk_texts.get(cluster_key, [])
                    sample_text = "<br>".join([
                        f"Sample {j+1}: {text[:100]}..." 
                        for j, text in enumerate(cluster_samples[:3])
                    ])
                    
                    hover_text = (
                        f"Segment {segment}, Cluster {cluster}<br>"
                        f"Used by {usage_count} vectors<br><br>"
                        f"Text Samples:<br>{sample_text}"
                    )
                    
                    G.add_node(i, pos=tuple(pos), 
                             text=hover_text,
                             size=usage_count)
            
            # Create figure
            fig = go.Figure()
            
            # Get node positions and sizes
            pos = nx.get_node_attributes(G, 'pos')
            sizes = nx.get_node_attributes(G, 'size')
            
            if not pos or not sizes:
                return self._create_fallback_visualization()
            
            # Add nodes
            node_x = [pos[node][0] for node in G.nodes()]
            node_y = [pos[node][1] for node in G.nodes()]
            node_z = [pos[node][2] for node in G.nodes()]
            node_text = [G.nodes[node]['text'] for node in G.nodes()]
            node_sizes = [sizes[node] for node in G.nodes()]
            
            # Scale node sizes
            min_size = 10
            max_size = 30
            scaled_sizes = [
                min_size + (max_size - min_size) * (size / max(node_sizes))
                for size in node_sizes
            ]
            
            # Add 3D scatter plot
            fig.add_trace(go.Scatter3d(
                x=node_x,
                y=node_y,
                z=node_z,
                mode='markers',
                marker=dict(
                    size=scaled_sizes,
                    color=list(range(len(node_x))),
                    colorscale='Viridis',
                    showscale=True
                ),
                text=node_text,
                hoverinfo='text',
                hovertemplate="%{text}<extra></extra>"
            ))
            
            # Update layout for 3D
            fig.update_layout(
                title='Document Embedding Clusters (3D)',
                showlegend=False,
                scene=dict(
                    xaxis_title='PCA 1',
                    yaxis_title='PCA 2',
                    zaxis_title='PCA 3',
                    camera=dict(
                        up=dict(x=0, y=0, z=1),
                        center=dict(x=0, y=0, z=0),
                        eye=dict(x=1.5, y=1.5, z=1.5)
                    )
                ),
                margin=dict(l=0, r=0, b=0, t=30),
                hoverlabel=dict(
                    bgcolor="white",
                    font_size=12,
                    font_family="Arial",
                    font=dict(color="black")
                )
            )
            
            return fig
            
        except Exception as e:
            logger.error(f"Error creating visualization: {str(e)}")
            return self._create_fallback_visualization()

    def _create_fallback_visualization(self) -> go.Figure:
        """Create a simple visualization for small documents"""
        fig = go.Figure()
        
        fig.add_trace(go.Scatter3d(
            x=[0], y=[0], z=[0],
            mode='markers+text',
            marker=dict(size=10),
            text=["Document too short for meaningful visualization"],
            hoverinfo='text'
        ))
        
        fig.update_layout(
            title='Document Embedding Visualization (Limited Data)',
            showlegend=False,
            scene=dict(
                xaxis_title='PCA 1',
                yaxis_title='PCA 2',
                zaxis_title='PCA 3'
            ),
            margin=dict(l=0, r=0, b=0, t=30)
        )
        
        return fig