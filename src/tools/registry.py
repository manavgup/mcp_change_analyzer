"""
Tool registry for Change Analyzer MCP server.
"""
import logging
from typing import Dict, List, Type, Any, Optional

from mcp_shared_lib.src.tools.base_tool import BaseTool
from src.tools.repo_analyzer import RepoAnalyzerTool
from src.tools.metrics_collector import MetricsCollectorTool
from src.lib.error.handler import MCPError
from mcp_shared_lib.src.tools.directory_analyzer_tool import DirectoryAnalyzer as SharedDirectoryAnalyzer

logger = logging.getLogger(__name__)


class ToolRegistryError(MCPError):
    """Exception raised for tool registry errors"""
    pass


class ToolRegistry:
    """Registry for MCP tools"""
    
    def __init__(self):
        """Initialize the tool registry"""
        self._tools: Dict[str, BaseTool] = {}
        self._tool_classes: Dict[str, Type[BaseTool]] = {
            'analyze_repository': RepoAnalyzerTool,
            'collect_metrics': MetricsCollectorTool,
            'analyze_directories': SharedDirectoryAnalyzer,
        }
        logger.info(f"Tool registry initialized with {len(self._tool_classes)} tool types")
    
    def register_tool(self, tool_name: str, tool: BaseTool) -> None:
        """
        Register a tool instance with the registry.
        
        Args:
            tool_name: Name of the tool
            tool: Tool instance
            
        Raises:
            ToolRegistryError: If a tool with the same name already exists
        """
        if tool_name in self._tools:
            raise ToolRegistryError(f"Tool '{tool_name}' already registered")
        
        self._tools[tool_name] = tool
        logger.info(f"Tool '{tool_name}' registered")
    
    def create_tool(self, 
                   tool_name: str, 
                   repo_path: str, 
                   **kwargs) -> BaseTool:
        """
        Create a new tool instance.
        
        Args:
            tool_name: Name of the tool to create
            repo_path: Path to the repository
            **kwargs: Additional arguments for tool initialization
            
        Returns:
            Tool instance
            
        Raises:
            ToolRegistryError: If the tool type is not found
        """
        if tool_name not in self._tool_classes:
            raise ToolRegistryError(f"Tool type '{tool_name}' not found")
        
        tool_class = self._tool_classes[tool_name]
        tool = tool_class(repo_path=repo_path, **kwargs)
        logger.info(f"Tool '{tool_name}' created for repository '{repo_path}'")
        return tool
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Get a tool instance by name.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(tool_name)
    
    def get_registered_tools(self) -> List[str]:
        """
        Get a list of registered tool names.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_available_tool_types(self) -> List[str]:
        """
        Get a list of available tool types.
        
        Returns:
            List of tool type names
        """
        return list(self._tool_classes.keys())
