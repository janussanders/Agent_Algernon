import os
from typing import Dict, Any
from dataclasses import dataclass
from pathlib import Path

@dataclass
class AppConfig:
    # Deployment
    deployment_type: str
    environment: str
    
    # API URLs
    service_url: str
    qdrant_host: str
    websocket_url: str
    
    # Streamlit Configuration
    streamlit_port: int
    streamlit_address: str
    streamlit_debug: bool
    
    # Qdrant Configuration
    qdrant_http_port: int
    qdrant_grpc_port: int
    qdrant_https: bool
    qdrant_verify_ssl: bool
    
    # Application Settings
    debug: bool
    python_path: str
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Create configuration from environment variables"""
        return cls(
            deployment_type=os.getenv('DEPLOYMENT_TYPE', 'local'),
            environment=os.getenv('ENVIRONMENT', 'development'),
            
            service_url=os.getenv('SERVICE_URL', 'http://localhost:8501'),
            qdrant_host=os.getenv('QDRANT_HOST', 'localhost'),
            websocket_url=os.getenv('WEBSOCKET_API_URL', 'ws://localhost:8501'),
            
            streamlit_port=int(os.getenv('STREAMLIT_SERVER_PORT', '8501')),
            streamlit_address=os.getenv('STREAMLIT_SERVER_ADDRESS', '0.0.0.0'),
            streamlit_debug=os.getenv('STREAMLIT_DEBUG', 'false').lower() == 'true',
            
            qdrant_http_port=int(os.getenv('QDRANT_HTTP_PORT', '6333')),
            qdrant_grpc_port=int(os.getenv('QDRANT_GRPC_PORT', '6334')),
            qdrant_https=os.getenv('QDRANT_HTTPS', 'false').lower() == 'true',
            qdrant_verify_ssl=os.getenv('QDRANT_VERIFY_SSL', 'false').lower() == 'true',
            
            debug=os.getenv('DEBUG', 'false').lower() == 'true',
            python_path=os.getenv('PYTHONPATH', '/app')
        )
    
    @property
    def is_production(self) -> bool:
        return self.environment == 'production'
    
    @property
    def is_local(self) -> bool:
        return self.environment == 'development'
    
    def get_qdrant_url(self) -> str:
        """Get the Qdrant URL with appropriate protocol"""
        protocol = 'https' if self.qdrant_https else 'http'
        return f"{protocol}://{self.qdrant_host}:{self.qdrant_http_port}"
    
    def get_websocket_url(self) -> str:
        """Get the WebSocket URL"""
        return self.websocket_url

# Global configuration instance
config = AppConfig.from_env() 