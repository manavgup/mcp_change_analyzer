"""
MCP server for Change Analyzer.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
import asyncio

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config.loader import ConfigLoader
from src.tools.registry import ToolRegistry
from src.lib.error.handler import MCPError, ErrorHandler
from src.lib.telemetry.monitor import Telemetry
from src.lib.state.manager import StateManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="MCP Change Analyzer Server")

# Initialize components
config_loader = ConfigLoader()
tool_registry = ToolRegistry()
error_handler = ErrorHandler()
telemetry = Telemetry(server_name="change-analyzer")
state_manager = StateManager(
    redis_url=config_loader.get("redis", "url", "redis://localhost:6379")
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Can be made more restrictive in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models for API
class ToolRequest(BaseModel):
    """Request model for tool execution"""
    repo_path: str
    arguments: Dict[str, Any] = {}


class ToolResponse(BaseModel):
    """Response model for tool execution"""
    result: Any
    metadata: Dict[str, Any] = {}


# Dependency for repository path validation
async def validate_repo_path(request: ToolRequest) -> str:
    """Validate the repository path"""
    repo_path = request.repo_path
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail=f"Repository path '{repo_path}' is not a valid directory")
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        raise HTTPException(status_code=400, detail=f"Repository path '{repo_path}' is not a Git repository")
    return repo_path


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "server": "mcp-change-analyzer"}


@app.get("/tools")
async def list_tools():
    """List available tools"""
    return {
        "available_tools": tool_registry.get_available_tool_types(),
        "registered_tools": tool_registry.get_registered_tools()
    }


@app.post("/tools/{tool_name}", response_model=ToolResponse)
@error_handler.with_retry(exceptions=(MCPError,))
@telemetry.track_tool_call(tool_name="execute_tool")
async def execute_tool(tool_name: str, request: ToolRequest, repo_path: str = Depends(validate_repo_path)):
    """
    Execute a tool with the given parameters.
    
    Args:
        tool_name: Name of the tool to execute
        request: Tool request parameters
        repo_path: Validated repository path (injected by dependency)
    
    Returns:
        ToolResponse with the tool execution result
    """
    logger.info(f"Executing tool '{tool_name}' for repository '{repo_path}'")
    
    # Get or create tool
    tool = tool_registry.get_tool(tool_name)
    if tool is None:
        try:
            tool = tool_registry.create_tool(tool_name, repo_path=repo_path)
            tool_registry.register_tool(tool_name, tool)
        except Exception as e:
            logger.error(f"Error creating tool '{tool_name}': {e}")
            raise HTTPException(status_code=500, detail=f"Error creating tool: {str(e)}")
    
    # Execute tool
    try:
        result = await tool.execute(**request.arguments)
        
        # Generate unique ID for this execution
        # In a real implementation, you would use a more robust ID generation strategy
        execution_id = f"{tool_name}_{id(result)}"
        
        # Save state if result is valid
        if result:
            await state_manager.save_workflow_state(execution_id, {
                "tool_name": tool_name,
                "repo_path": repo_path,
                "arguments": request.arguments,
                "timestamp": asyncio.get_event_loop().time(),
            })
        
        # Parse result as JSON if it's a string
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                # Keep as string if not valid JSON
                pass
        
        return ToolResponse(
            result=result,
            metadata={
                "execution_id": execution_id,
                "tool_name": tool_name,
                "repo_path": repo_path,
            }
        )
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error executing tool: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for all unhandled exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return Response(
        status_code=500,
        content=json.dumps({"detail": str(exc)}),
        media_type="application/json"
    )


if __name__ == "__main__":
    # Run the server
    import uvicorn
    
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"Starting MCP Change Analyzer server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
