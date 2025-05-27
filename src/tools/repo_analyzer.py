"""
Repository analyzer tool for Change Analyzer MCP server.
"""
import json
import time
from typing import Optional, Dict, Any, Type
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

import logging
logger = logging.getLogger(__name__)

from src.lib.models.git_models import RepositoryAnalysis
from src.tools.base_tool import BaseRepoTool


class RepoAnalyzerSchema(BaseModel):
    """Input schema for Repository Analyzer Tool."""
    max_files: Optional[int] = Field(None, description="Maximum number of files to analyze")
    use_summarization: Optional[bool] = Field(True, description="Whether to summarize large diffs")
    max_diff_size: Optional[int] = Field(2000, description="Maximum size of diffs in characters")


class RepoAnalyzerTool(BaseRepoTool):
    """Tool for analyzing a git repository using GitService."""

    name: str = "Repository Analyzer"
    description: str = """
    Analyzes the git repository (path provided during setup) to extract metadata and changes.
    Identifies files that have been modified, their directories, and change statistics.
    Helps understand the structure and scale of changes in a repository.
    """
    
    async def execute(
        self,
        max_files: Optional[int] = None,
        use_summarization: Optional[bool] = True,
        max_diff_size: Optional[int] = 2000
    ) -> str:
        """
        Analyze the git repository using the initialized GitService instance.

        Args:
            max_files: Maximum number of files to analyze.
            use_summarization: Whether to summarize large diffs.
            max_diff_size: Maximum size of diffs in characters.

        Returns:
            A JSON string serialization of the RepositoryAnalysis object.
        """
        start_time = time.time()
        logger.info(f"Starting repository analysis with max_files={max_files}, use_summarization={use_summarization}, max_diff_size={max_diff_size}")

        # Check if git_service was successfully initialized
        if not hasattr(self, 'git_service') or not self.git_service:
            logger.error(f"CRITICAL: GitService not available in {self.name}. Tool cannot operate.")
            error_data = {"error": f"Tool {self.name} failed: GitService not available."}
            return json.dumps(error_data)

        # Use the repo_path from the initialized git_service instance
        repo_path = self._repo_path
        logger.info(f"Analyzing repository '{repo_path}'")

        try:
            # Use the analyze_repository function from the initialized git_service
            analysis: RepositoryAnalysis = await self.git_service.analyze_repository(
                max_files=max_files,
                use_summarization=use_summarization,
                max_diff_size=max_diff_size,
            )

            # Ensure the repo_path in the result matches the one used
            if analysis.repo_path != repo_path:
                logger.warning(f"Repo path mismatch in analysis result. Expected '{repo_path}', got '{analysis.repo_path}'. Overwriting.")
                analysis.repo_path = repo_path

            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"Analysis complete for {repo_path}. Files processed: {analysis.total_files_changed}. Duration: {duration:.2f} seconds")
            
            # Return JSON string
            return analysis.model_dump_json(indent=2)

        except ValidationError as ve:
            # Error likely occurred within git_service.analyze_repository creating the model
            error_msg = f"Pydantic validation error during analysis for '{repo_path}': {str(ve)}"
            logger.error(error_msg, exc_info=True)
            # Return a minimal valid result as JSON string in case of error
            error_analysis = RepositoryAnalysis(
                repo_path=repo_path,
                error=error_msg
            )
            return error_analysis.model_dump_json(indent=2)
        except Exception as e:
            error_msg = f"Error analyzing repository '{repo_path}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Return a minimal valid result as JSON string in case of error
            error_analysis = RepositoryAnalysis(
                repo_path=repo_path,
                error=f"Analysis failed: {str(e)}"
            )
            return error_analysis.model_dump_json(indent=2)
