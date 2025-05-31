"""
Analysis Service - Provides repository analysis functionality
"""
import os
import logging
from typing import Dict, Any, List, Optional
import asyncio
import json

logger = logging.getLogger(__name__)

class AnalysisService:
    """Service for repository analysis"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Analysis service with configuration"""
        self.config = config
        self.analysis_config = config.get('analysis', {})
        self.max_files_per_analysis = self.analysis_config.get('max_files_per_analysis', 1000)
        
        # Import GitService here to avoid circular imports
        from src.services.git_service import GitService
        self.git_service = GitService
        
        logger.info(f"Analysis service initialized with max_files_per_analysis: {self.max_files_per_analysis}")
    
    async def analyze_repository(
        self, 
        repo_path: str, 
        max_files: Optional[int] = None, 
        include_untracked: bool = True,
        verbose: int = 0
    ) -> Dict[str, Any]:
        """
        Analyze uncommitted changes in a repository
        
        Args:
            repo_path: Path to the local git repository
            max_files: Maximum number of changed files to analyze fully
            include_untracked: Whether to include untracked files
            verbose: Increase verbosity level (0, 1, or 2)
            
        Returns:
            Analysis results including changed files, directory structure, and metrics
        """
        logger.info(f"Analyzing repository: {repo_path}")
        
        # Use provided max_files or default from config
        max_files = max_files or self.max_files_per_analysis
        
        try:
            # Get changed files
            changed_files_result = await self.git_service.get_changed_files(
                repo_path=repo_path,
                include_untracked=include_untracked
            )
            
            # Get repository metrics
            metrics_result = await self.git_service.get_metrics(
                repo_path=repo_path,
                metrics=["file_count", "changes", "languages", "contributors"]
            )
            
            # Get directory structure
            directory_structure = await self.analyze_directory_structure(
                repo_path=repo_path,
                max_depth=3
            )
            
            # Analyze patterns in changed files
            patterns = await self.analyze_patterns(
                repo_path=repo_path,
                changed_files=changed_files_result["files"]
            )
            
            # Combine all results
            result = {
                "repository": {
                    "path": repo_path,
                    "metrics": metrics_result
                },
                "changes": changed_files_result,
                "directory_structure": directory_structure,
                "patterns": patterns
            }
            
            # Add verbose information if requested
            if verbose > 0:
                result["verbose"] = {
                    "level": verbose,
                    "config": self.analysis_config
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing repository: {e}")
            raise
    
    async def analyze_directory_structure(
        self, 
        repo_path: str, 
        max_depth: int = 3
    ) -> Dict[str, Any]:
        """
        Analyze repository directory structure
        
        Args:
            repo_path: Path to the local git repository
            max_depth: Maximum depth of directory tree to analyze
            
        Returns:
            Directory structure analysis
        """
        logger.info(f"Analyzing directory structure: {repo_path}")
        
        try:
            # Build directory tree
            tree = await self._build_directory_tree(repo_path, max_depth)
            
            # Analyze directory relationships
            relationships = await self._analyze_directory_relationships(tree)
            
            return {
                "tree": tree,
                "relationships": relationships,
                "max_depth": max_depth
            }
            
        except Exception as e:
            logger.error(f"Error analyzing directory structure: {e}")
            raise
    
    async def analyze_patterns(
        self, 
        repo_path: str, 
        changed_files: Dict[str, List[Any]]
    ) -> Dict[str, Any]:
        """
        Analyze patterns in file changes
        
        Args:
            repo_path: Path to the local git repository
            changed_files: Dictionary of changed files by category
            
        Returns:
            Pattern analysis results
        """
        logger.info(f"Analyzing patterns in changed files")
        
        try:
            # Flatten the list of changed files
            all_files = []
            for category, files in changed_files.items():
                if category == "renamed":
                    # Handle renamed files differently
                    for rename_info in files:
                        all_files.append(rename_info["new_path"])
                else:
                    all_files.extend(files)
            
            # Group files by directory
            directory_groups = {}
            for file_path in all_files:
                directory = os.path.dirname(file_path)
                if directory not in directory_groups:
                    directory_groups[directory] = []
                directory_groups[directory].append(file_path)
            
            # Group files by extension
            extension_groups = {}
            for file_path in all_files:
                _, ext = os.path.splitext(file_path)
                ext = ext.lower() if ext else "no_extension"
                if ext not in extension_groups:
                    extension_groups[ext] = []
                extension_groups[ext].append(file_path)
            
            # Identify potential logical groups
            logical_groups = await self._identify_logical_groups(repo_path, all_files)
            
            return {
                "directory_groups": directory_groups,
                "extension_groups": extension_groups,
                "logical_groups": logical_groups,
                "total_files_analyzed": len(all_files)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            raise
    
    async def _build_directory_tree(self, repo_path: str, max_depth: int) -> Dict[str, Any]:
        """Build a tree representation of the repository directory structure"""
        tree = {"name": os.path.basename(repo_path), "type": "directory", "children": []}
        
        async def _build_tree(directory, parent_node, current_depth):
            if current_depth > max_depth:
                return
            
            try:
                entries = os.listdir(directory)
            except PermissionError:
                return
            
            for entry in sorted(entries):
                path = os.path.join(directory, entry)
                rel_path = os.path.relpath(path, repo_path)
                
                # Skip .git directory and other excluded patterns
                if self._should_exclude(rel_path):
                    continue
                
                if os.path.isdir(path):
                    # Directory
                    dir_node = {
                        "name": entry,
                        "type": "directory",
                        "path": rel_path,
                        "children": []
                    }
                    parent_node["children"].append(dir_node)
                    
                    # Recursively process subdirectories
                    await _build_tree(path, dir_node, current_depth + 1)
                else:
                    # File
                    _, ext = os.path.splitext(entry)
                    file_node = {
                        "name": entry,
                        "type": "file",
                        "path": rel_path,
                        "extension": ext.lower() if ext else None
                    }
                    parent_node["children"].append(file_node)
        
        await _build_tree(repo_path, tree, 1)
        return tree
    
    async def _analyze_directory_relationships(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze relationships between directories"""
        # Extract all directories
        directories = []
        
        def _extract_directories(node, parent_path=""):
            if node["type"] == "directory":
                path = os.path.join(parent_path, node["name"])
                if "path" in node:
                    directories.append(node["path"])
                elif path:
                    directories.append(path)
                
                for child in node.get("children", []):
                    _extract_directories(child, path)
        
        _extract_directories(tree)
        
        # Analyze parent-child relationships
        relationships = {
            "parent_child": [],
            "siblings": []
        }
        
        for i, dir1 in enumerate(directories):
            for dir2 in directories[i+1:]:
                if os.path.dirname(dir2) == dir1:
                    relationships["parent_child"].append({
                        "parent": dir1,
                        "child": dir2
                    })
                elif os.path.dirname(dir1) == os.path.dirname(dir2):
                    relationships["siblings"].append([dir1, dir2])
        
        return relationships
    
    async def _identify_logical_groups(self, repo_path: str, files: List[str]) -> List[Dict[str, Any]]:
        """Identify potential logical groups of files"""
        # Simple grouping based on common prefixes
        prefix_groups = {}
        
        for file_path in files:
            # Skip files at the root level
            if "/" not in file_path and "\\" not in file_path:
                continue
            
            # Get the top-level directory or component name
            parts = file_path.replace("\\", "/").split("/")
            if len(parts) > 1:
                prefix = parts[0]
                if prefix not in prefix_groups:
                    prefix_groups[prefix] = []
                prefix_groups[prefix].append(file_path)
        
        # Convert to list of groups
        logical_groups = []
        for prefix, group_files in prefix_groups.items():
            if len(group_files) > 1:  # Only include groups with multiple files
                logical_groups.append({
                    "name": prefix,
                    "files": group_files,
                    "count": len(group_files)
                })
        
        # Sort by number of files (descending)
        logical_groups.sort(key=lambda x: x["count"], reverse=True)
        
        return logical_groups
    
    def _should_exclude(self, file_path: str) -> bool:
        """Check if a file should be excluded based on patterns"""
        import fnmatch
        
        # Get exclude patterns from config
        exclude_patterns = self.analysis_config.get('exclude_patterns', [])
        
        # Check against exclude patterns
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        
        # Also exclude .git directory
        if '.git' in file_path.split(os.path.sep):
            return True
        
        return False
