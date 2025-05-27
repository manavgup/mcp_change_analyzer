import os
import yaml
from typing import Dict, Any, Optional

class ConfigLoader:
    """Configuration loader for MCP servers"""

    def __init__(self, config_path: str = None):
        """Initialize with optional path to config file"""
        self.config_path = config_path or os.environ.get("CONFIG_PATH", "config/server.yaml")
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return {}

    def get(self, section: str, key: Optional[str] = None, default: Any = None) -> Any:
        """Get configuration value by section and optional key"""
        if section not in self.config:
            return default
        
        if key is None:
            return self.config[section]
        
        return self.config[section].get(key, default)
