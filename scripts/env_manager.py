#!/usr/bin/env python3

import os
import sys
from pathlib import Path
from loguru import logger
import yaml
from typing import Dict, Any, Optional

class EnvironmentManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.env_dir = self.config_dir / "env"
        
    def load_env_file(self, env_file: Path) -> Dict[str, str]:
        """Load environment variables from a file"""
        env_vars = {}
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        return env_vars
    
    def get_existing_api_key(self) -> Optional[str]:
        """Get existing API key from current .env"""
        env_path = self.project_root / ".env"
        if env_path.exists():
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.startswith('SAMBANOVA_API_KEY='):
                            return line.split('=')[1].strip()
            except Exception as e:
                logger.warning(f"Could not read existing .env file: {e}")
        return None
    
    def create_env_file(self, env_type: str = "local") -> bool:
        """Create .env file with required variables"""
        try:
            # Load base environment variables
            base_env = self.load_env_file(self.env_dir / "base.env")
            
            # Load environment-specific variables
            env_specific = self.load_env_file(self.env_dir / f"{env_type}.env")
            
            # Merge environment variables
            env_vars = {**base_env, **env_specific}
            
            # Handle sensitive data
            if "SAMBANOVA_API_KEY" not in env_vars:
                existing_key = self.get_existing_api_key()
                if existing_key:
                    env_vars["SAMBANOVA_API_KEY"] = existing_key
                else:
                    api_key = input("Enter your SambaNova API key: ").strip()
                    if not api_key:
                        raise ValueError("API key cannot be empty")
                    env_vars["SAMBANOVA_API_KEY"] = api_key
            
            # Write environment files
            self.write_env_file(env_vars, ".env")
            self.write_env_file(env_vars, "docker/.env")
            
            # Set variables in current environment
            os.environ.update(env_vars)
            
            logger.success(f"Environment files created successfully for {env_type}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create environment files: {str(e)}")
            return False
    
    def write_env_file(self, env_vars: Dict[str, str], target_path: str) -> None:
        """Write environment variables to specified file"""
        target = self.project_root / target_path
        target.parent.mkdir(parents=True, exist_ok=True)
        
        with open(target, "w") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        
        # Set appropriate permissions
        target.chmod(0o600)

def main():
    env_manager = EnvironmentManager()
    
    # Determine environment type from command line or default to local
    env_type = sys.argv[1] if len(sys.argv) > 1 else "local"
    
    if env_type not in ["local", "prod"]:
        logger.error("Invalid environment type. Use 'local' or 'prod'")
        sys.exit(1)
    
    if not env_manager.create_env_file(env_type):
        sys.exit(1)

if __name__ == "__main__":
    main() 