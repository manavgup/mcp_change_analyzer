"""
Base tool implementations for the Change Analyzer MCP server.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Set, Type, Union
import re
import os
from pathlib import Path

import time
import json
from pydantic import BaseModel, ConfigDict, ValidationError

# Import mcp-change-analyzer specific models and services
from src.lib.models.git_models import RepositoryAnalysis
from src.services.git_service import GitService
from src.lib.error.handler import MCPError

# Setup logging
import logging
logger = logging.getLogger(__name__)


class BaseToolError(MCPError):
    """Base exception for tool errors."""
    pass


class BaseTool(ABC):
    """Base class for all MCP tools."""
    
    name: str = "Base Tool"
    description: str = "Base tool implementation for MCP servers."
    
    model_config = ConfigDict(arbitrary_types_allowed=True,
                             extra='allow')
    
    def __init__(self, **kwargs):
        """Initialize the tool."""
        # Set any provided attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool functionality."""
        pass
    
    def _clean_json_string(self, json_str: str) -> str:
        """Clean a JSON string by removing potential code block formatting, trailing backticks, and control characters."""
        if not isinstance(json_str, str):
            return "{}"  # Return empty JSON if not a string
        
        # Remove control characters (except allowed ones like \n, \t, etc.)
        json_str = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_str)
        
        # Find the beginning of the JSON object
        start_pattern = r'{\s*"'
        start_match = re.search(start_pattern, json_str)
        if start_match:
            start_pos = start_match.start()
            json_str = json_str[start_pos:]  # Start from the actual JSON object
        
        # Find where the JSON object should end
        # This uses a simple approach - count matching braces
        open_braces = 0
        close_pos = -1
        
        for i, char in enumerate(json_str):
            if char == '{':
                open_braces += 1
            elif char == '}':
                open_braces -= 1
                if open_braces == 0:
                    close_pos = i + 1  # Include the closing brace
                    break
        
        if close_pos > 0:
            json_str = json_str[:close_pos]  # Extract just the complete JSON object
        
        # Strip any Markdown formatting
        json_str = re.sub(r'```json\s*', '', json_str)
        json_str = re.sub(r'```\s*$', '', json_str)
        json_str = json_str.strip()
        
        # Remove any trailing backticks
        if json_str.endswith('`'):
            json_str = json_str.rstrip('`')
        
        # Validate the string is parseable JSON
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            # If we can't parse it, return a minimal valid JSON object
            logger.error("JSON cleaning failed to produce valid JSON")
            return "{}"
    
    def _validate_json_string(self, json_str: str) -> bool:
        """
        Validate that a string is proper JSON.
        
        Args:
            json_str: The JSON string to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not json_str or not isinstance(json_str, str):
            return False
            
        # Clean the JSON string
        json_str = self._clean_json_string(json_str)
        
        # Check if it starts with a JSON object or array
        if not json_str.strip().startswith('{') and not json_str.strip().startswith('['):
            return False
            
        # Try to parse it
        try:
            json.loads(json_str)
            return True
        except json.JSONDecodeError:
            return False
    
    def _safe_deserialize(self, json_str: str, model_cls: Optional[Type[BaseModel]] = None) -> Dict[str, Any]:
        """
        Safely deserialize JSON to a dictionary or Pydantic model with proper error handling.
        
        Args:
            json_str: The JSON string to deserialize
            model_cls: Optional Pydantic model class to validate against
            
        Returns:
            Dictionary representation of the JSON
            
        Raises:
            ValueError: If json_str is not valid JSON
        """
        if not self._validate_json_string(json_str):
            raise ValueError("Invalid JSON string provided")
            
        # Clean the JSON string
        json_str = self._clean_json_string(json_str)
        
        # Parse to dictionary
        parsed_data = json.loads(json_str)
        
        # Validate against model if provided
        if model_cls is not None:
            try:
                validated = model_cls.model_validate(parsed_data)
                return validated.model_dump()
            except ValidationError as e:
                logger.warning(f"Validation error in _safe_deserialize: {e}")
                # Return original parsed data if validation fails
                return parsed_data
        
        return parsed_data


class BaseRepoTool(BaseTool):
    """Base class for repository analysis tools."""
    
    # Class-level cache across all instances
    _git_service_cache = {}
    
    def __init__(self, repo_path: str, **kwargs):
        """
        Initialize the tool and the GitService instance.
        
        Args:
            repo_path: Path to the git repository
            **kwargs: Additional keyword arguments
        """
        super().__init__(**kwargs)
        
        # Store repo_path locally
        self._repo_path = str(Path(repo_path).resolve())
        
        # Initialize GitService instance
        if self._repo_path not in self._git_service_cache:
            logger.info(f"Creating new GitService instance for: {self._repo_path} (Tool: {self.name})")
            try:
                self._git_service_cache[self._repo_path] = GitService(self._repo_path)
            except Exception as e:
                logger.error(f"Failed to initialize GitService: {e}")
                raise
        
        # Store git_service in private attribute
        self._git_service = self._git_service_cache[self._repo_path]
    
    # Property to access git_service
    @property
    def git_service(self) -> GitService:
        return self._git_service
    
    def _extract_file_paths(self, repository_analysis_json: str) -> List[str]:
        """
        Extract file paths from repository analysis JSON.
        
        Args:
            repository_analysis_json: JSON string of RepositoryAnalysis
            
        Returns:
            List of file paths
        """
        try:
            # Clean the input
            repository_analysis_json = self._clean_json_string(repository_analysis_json)
            
            # Try to parse it as JSON
            data = json.loads(repository_analysis_json)
            
            # Now extract file paths
            file_paths = []
            if "file_changes" in data and isinstance(data["file_changes"], list):
                for file_change in data["file_changes"]:
                    if isinstance(file_change, dict) and "path" in file_change:
                        path = file_change["path"]
                        if path and isinstance(path, str):
                            file_paths.append(path)
            
            logger.info(f"Extracted {len(file_paths)} file paths from repository analysis")
            return file_paths
        except Exception as e:
            logger.error(f"Error extracting file paths: {e}")
            return []
    
    def _extract_directory_mapping(self, repository_analysis_json: str) -> Dict[str, List[str]]:
        """
        Extract directory to files mapping from repository analysis JSON.
        
        Args:
            repository_analysis_json: JSON string of RepositoryAnalysis
            
        Returns:
            Dictionary mapping directories to lists of file paths
        """
        try:
            data = self._safe_deserialize(repository_analysis_json)
            directory_to_files = {}
            
            # Try to extract from file_changes
            if "file_changes" in data and isinstance(data["file_changes"], list):
                for file_change in data["file_changes"]:
                    if not isinstance(file_change, dict) or "path" not in file_change:
                        continue
                        
                    path = file_change["path"]
                    if not path or not isinstance(path, str):
                        continue
                    
                    # Get directory from the path or from the directory field if available
                    if "directory" in file_change and file_change["directory"]:
                        directory = file_change["directory"]
                    else:
                        # Extract directory from path
                        directory = os.path.dirname(path)
                        if not directory:
                            directory = "(root)"
                    
                    # Add to mapping
                    if directory not in directory_to_files:
                        directory_to_files[directory] = []
                    directory_to_files[directory].append(path)
            
            # Try to extract from directory_summaries
            elif "directory_summaries" in data and isinstance(data["directory_summaries"], list):
                for dir_summary in data["directory_summaries"]:
                    if not isinstance(dir_summary, dict) or "path" not in dir_summary:
                        continue
                        
                    directory = dir_summary["path"]
                    if not directory or not isinstance(directory, str):
                        continue
                        
                    if "files" in dir_summary and isinstance(dir_summary["files"], list):
                        directory_to_files[directory] = dir_summary["files"]
            
            return directory_to_files
        except Exception as e:
            logger.error(f"Error extracting directory mapping: {e}")
            return {}
    
    def _extract_file_metadata(self, repository_analysis_json: str) -> List[Dict[str, Any]]:
        """
        Extract lightweight file metadata from repository analysis JSON.
        
        Args:
            repository_analysis_json: JSON string of RepositoryAnalysis
            
        Returns:
            List of dictionaries with file metadata (path, extension, directory, changes)
        """
        try:
            data = self._safe_deserialize(repository_analysis_json)
            file_metadata = []
            
            # Find file_changes in the data
            if "file_changes" in data and isinstance(data["file_changes"], list):
                for file_change in data["file_changes"]:
                    if not isinstance(file_change, dict) or "path" not in file_change:
                        continue
                        
                    path = file_change["path"]
                    if not path or not isinstance(path, str):
                        continue
                    
                    # Create metadata dict with required fields
                    metadata = {
                        "path": path,
                        "directory": file_change.get("directory", os.path.dirname(path) or "(root)"),
                        "extension": file_change.get("extension", os.path.splitext(path)[1]),
                        "name": os.path.basename(path)
                    }
                    
                    # Add changes if available
                    if "changes" in file_change and isinstance(file_change["changes"], dict):
                        changes = file_change["changes"]
                        metadata["added_lines"] = changes.get("added", 0)
                        metadata["deleted_lines"] = changes.get("deleted", 0)
                        metadata["total_changes"] = changes.get("added", 0) + changes.get("deleted", 0)
                    else:
                        metadata["added_lines"] = 0
                        metadata["deleted_lines"] = 0
                        metadata["total_changes"] = 0
                    
                    # Add status if available
                    if "staged_status" in file_change:
                        metadata["staged_status"] = file_change["staged_status"]
                    if "unstaged_status" in file_change:
                        metadata["unstaged_status"] = file_change["unstaged_status"]
                    
                    file_metadata.append(metadata)
            
            return file_metadata
        except Exception as e:
            logger.error(f"Error extracting file metadata: {e}")
            return []
    
    def _extract_directory_summaries(self, repository_analysis_json: str) -> List[Dict[str, Any]]:
        """
        Extract directory summaries from repository analysis JSON.
        
        Args:
            repository_analysis_json: JSON string of RepositoryAnalysis
            
        Returns:
            List of dictionaries with directory summaries
        """
        try:
            data = self._safe_deserialize(repository_analysis_json)
            
            # Find directory_summaries in the data
            if "directory_summaries" in data and isinstance(data["directory_summaries"], list):
                summaries = []
                for summary in data["directory_summaries"]:
                    if not isinstance(summary, dict) or "path" not in summary:
                        continue
                    
                    # Extract the basic info we need
                    dir_data = {
                        "path": summary["path"],
                        "file_count": summary.get("file_count", 0),
                        "total_changes": summary.get("total_changes", 0),
                        "extensions": summary.get("extensions", {})
                    }
                    
                    # Add depth calculation
                    path = summary["path"]
                    if path == "(root)":
                        dir_data["depth"] = 0
                    else:
                        dir_data["depth"] = path.count(os.path.sep) + 1
                    
                    summaries.append(dir_data)
                
                return summaries
            
            return []
        except Exception as e:
            logger.error(f"Error extracting directory summaries: {e}")
            return []
    
    def _extract_repository_info(self, repository_analysis_json: str) -> Dict[str, Any]:
        """
        Extract basic repository information from repository analysis JSON.
        
        Args:
            repository_analysis_json: JSON string of RepositoryAnalysis
            
        Returns:
            Dictionary with repository information
        """
        try:
            data = self._safe_deserialize(repository_analysis_json)
            
            # Extract basic repository info
            repo_info = {
                "repo_path": data.get("repo_path", self._repo_path),
                "total_files_changed": data.get("total_files_changed", 0),
                "total_lines_changed": data.get("total_lines_changed", 0)
            }
            
            # Extract extensions summary if available
            if "extensions_summary" in data and isinstance(data["extensions_summary"], dict):
                repo_info["extensions_summary"] = data["extensions_summary"]
            
            return repo_info
        except Exception as e:
            logger.error(f"Error extracting repository info: {e}")
            return {
                "repo_path": self._repo_path,
                "total_files_changed": 0,
                "total_lines_changed": 0
            }
