from typing import Optional
import os
import json
import logging
from pathlib import Path
from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

class APIService:
    """Service class for handling API key management."""
    
    def __init__(self):
        self.key_file = Path("data/api_key.enc")
        self.salt_file = Path("data/salt.key")
        self._ensure_data_dir()
        
    def _ensure_data_dir(self):
        """Ensure the data directory exists."""
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        
    def _generate_key(self, password: str) -> bytes:
        """Generate an encryption key from a password.
        
        Args:
            password: User password for key generation
            
        Returns:
            bytes: Generated encryption key
        """
        # Generate a salt if it doesn't exist
        if not self.salt_file.exists():
            salt = os.urandom(16)
            self.salt_file.write_bytes(salt)
        else:
            salt = self.salt_file.read_bytes()
            
        # Generate key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
        
    def save_api_key(self, api_key: str, password: str) -> bool:
        """Save the API key securely.
        
        Args:
            api_key: The API key to save
            password: Password for encryption
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Generate encryption key
            key = self._generate_key(password)
            f = Fernet(key)
            
            # Encrypt API key
            encrypted_data = f.encrypt(api_key.encode())
            
            # Save encrypted data
            self.key_file.write_bytes(encrypted_data)
            
            logger.info("API key saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save API key: {str(e)}")
            return False
            
    def load_api_key(self, password: str) -> Optional[str]:
        """Load the API key securely.
        
        Args:
            password: Password for decryption
            
        Returns:
            Optional[str]: The API key if successful, None otherwise
        """
        try:
            if not self.key_file.exists():
                return None
                
            # Generate decryption key
            key = self._generate_key(password)
            f = Fernet(key)
            
            # Load and decrypt API key
            encrypted_data = self.key_file.read_bytes()
            decrypted_data = f.decrypt(encrypted_data)
            
            return decrypted_data.decode()
            
        except Exception as e:
            logger.error(f"Failed to load API key: {str(e)}")
            return None
            
    def has_saved_key(self) -> bool:
        """Check if an API key is saved.
        
        Returns:
            bool: True if a key exists, False otherwise
        """
        return self.key_file.exists() 