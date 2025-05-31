"""
Git operations service for Change Analyzer MCP server.
Handles interaction with git repositories and provides change analysis.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
import asyncio
import subprocess
import logging

from ..mcp_shared_lib.src.models.git_models import (
    FileChange,
    LineChanges,
    FileStatusType,
    FileType,
    DiffSummary,
)
from mcp_shared_lib.src.models.analysis_models import (
    RepositoryAnalysis,
    DirectorySummary,
)
from src.lib.error.handler import MCPError

logger = logging.getLogger(__name__)


class GitError(MCPError):
    """Exception raised for Git operation errors"""

    pass


class GitService:
    """Service for Git operations and repository analysis"""

    def __init__(self, repo_path: str):
        """
        Initialize with path to Git repository.

        Args:
            repo_path: Path to Git repository

        Raises:
            GitError: If the path is not a valid Git repository
        """
        self.repo_path = os.path.abspath(repo_path)

        # Validate repository
        if not self._is_git_repo():
            raise GitError(f"Path '{repo_path}' is not a valid Git repository")

        logger.info(f"GitService initialized for repository: {self.repo_path}")

    def _is_git_repo(self) -> bool:
        """Check if the path is a valid Git repository"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except Exception as e:
            logger.error(f"Error checking Git repository: {e}")
            return False

    async def _run_git_command(self, args: List[str]) -> str:
        """
        Run a Git command asynchronously.

        Args:
            args: List of command arguments to pass to git

        Returns:
            Command output as string

        Raises:
            GitError: If the command fails
        """
        cmd = ["git"] + args
        logger.debug(f"Running Git command: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = (
                    f"Git command failed: {' '.join(cmd)}\nError: {stderr.strip()}"
                )
                logger.error(error_msg)
                raise GitError(error_msg)

            return stdout.strip()
        except asyncio.SubprocessError as e:
            error_msg = f"Error executing Git command: {' '.join(cmd)}\nError: {str(e)}"
            logger.error(error_msg)
            raise GitError(error_msg)

    async def get_current_branch(self) -> str:
        """Get the name of the current branch"""
        try:
            return await self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        except GitError:
            logger.warning("Failed to get current branch, returning 'unknown'")
            return "unknown"

    async def get_changed_files(self) -> List[FileChange]:
        """
        Get a list of files that have been changed in the repository.

        Returns:
            List of FileChange objects representing changed files
        """
        try:
            # Get the status of files in the repository
            status_output = await self._run_git_command(["status", "--porcelain=v1"])

            # Parse the status output into FileChange objects
            file_changes = []
            for line in status_output.splitlines():
                if not line or len(line) < 3:
                    continue

                # Extract the status codes and filename
                staged_status = line[0]
                unstaged_status = line[1]
                file_path = line[3:].strip()

                # Handle renamed files (R100 filename -> new_filename)
                original_path = None
                if staged_status == "R" and " -> " in file_path:
                    parts = file_path.split(" -> ")
                    if len(parts) == 2:
                        original_path = parts[0]
                        file_path = parts[1]

                # Create FileChange object
                file_change = FileChange(
                    path=str(file_path),  # Convert to string to match shared lib model
                    staged_status=(
                        FileStatusType(staged_status)
                        if staged_status != " "
                        else FileStatusType.NONE
                    ),
                    unstaged_status=(
                        FileStatusType(unstaged_status)
                        if unstaged_status != " "
                        else FileStatusType.NONE
                    ),
                    original_path=original_path,
                    file_type=await self._determine_file_type(file_path),
                )

                # Get line changes for the file
                changes = await self._get_line_changes(file_path)
                if changes:
                    file_change.changes = changes

                file_changes.append(file_change)

            return file_changes
        except GitError as e:
            logger.error(f"Error getting changed files: {e}")
            return []

    async def _determine_file_type(self, file_path: str) -> FileType:
        """
        Determine the type of a file (text or binary).

        Args:
            file_path: Path to the file relative to the repository root

        Returns:
            FileType enum value
        """
        # Check if the file exists
        full_path = os.path.join(self.repo_path, file_path)
        if not os.path.exists(full_path):
            return FileType.UNKNOWN

        try:
            # Use Git to determine if the file is binary
            result = subprocess.run(
                ["git", "diff", "--no-index", "--numstat", "/dev/null", file_path],
                cwd=self.repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            # If the first two fields are "-" and "-", the file is binary
            if result.stdout.strip().startswith("-\t-\t"):
                return FileType.BINARY

            return FileType.TEXT
        except Exception:
            # Default to text if we can't determine
            return FileType.TEXT

    async def _get_line_changes(self, file_path: str) -> Optional[LineChanges]:
        """
        Get line changes (added and deleted) for a file.

        Args:
            file_path: Path to the file relative to the repository root

        Returns:
            LineChanges object or None if couldn't determine
        """
        try:
            # Use Git to get the number of added and deleted lines
            result = await self._run_git_command(["diff", "--numstat", file_path])

            # Parse the output
            if result and "\t" in result:
                parts = result.split("\t", 2)
                if len(parts) >= 2:
                    try:
                        added = int(parts[0]) if parts[0] != "-" else 0
                        deleted = int(parts[1]) if parts[1] != "-" else 0
                        return LineChanges(added=added, deleted=deleted)
                    except (ValueError, TypeError):
                        pass

            return None
        except GitError:
            return None

    async def analyze_repository(
        self,
        max_files: Optional[int] = None,
        use_summarization: bool = True,
        max_diff_size: int = 2000,
    ) -> RepositoryAnalysis:
        """
        Analyze the repository to extract metadata and changes.

        Args:
            max_files: Maximum number of files to analyze
            use_summarization: Whether to summarize large diffs
            max_diff_size: Maximum size of diffs in characters

        Returns:
            RepositoryAnalysis object with analysis results
        """
        start_time = logger.info("Starting repository analysis")

        try:
            # Get changed files
            file_changes = await self.get_changed_files()
            if max_files and len(file_changes) > max_files:
                file_changes = file_changes[:max_files]

            # Count total changes
            total_files_changed = len(file_changes)
            total_lines_changed = sum(
                file_change.changes.total if file_change.changes else 0
                for file_change in file_changes
            )

            # Generate directory summaries
            directory_summaries = self._generate_directory_summaries(file_changes)

            # Create RepositoryAnalysis object
            analysis = RepositoryAnalysis(
                repo_path=str(self.repo_path),  # Ensure it's a string
                file_changes=file_changes,
                directory_summaries=directory_summaries,
                total_files_changed=total_files_changed,
                total_lines_changed=total_lines_changed,
            )

            logger.info(
                f"Repository analysis complete. Files: {total_files_changed}, Lines: {total_lines_changed}"
            )
            return analysis
        except Exception as e:
            logger.error(f"Error during repository analysis: {e}", exc_info=True)
            # Return a minimal analysis with error information
            return RepositoryAnalysis(
                repo_path=str(self.repo_path), error=f"Analysis failed: {str(e)}"
            )

    def _generate_directory_summaries(
        self, file_changes: List[FileChange]
    ) -> List[DirectorySummary]:
        """
        Generate summaries for directories with changes.

        Args:
            file_changes: List of file changes

        Returns:
            List of DirectorySummary objects
        """
        # Group files by directory
        directory_map: Dict[str, List[FileChange]] = {}
        for file_change in file_changes:
            directory = str(file_change.directory)  # Ensure it's a string
            if directory not in directory_map:
                directory_map[directory] = []
            directory_map[directory].append(file_change)

        # Create summaries
        summaries = []
        for directory, files in directory_map.items():
            # Count files by extension
            extensions: Dict[str, int] = {}
            for file_change in files:
                ext = file_change.extension or "(none)"
                extensions[ext] = extensions.get(ext, 0) + 1

            # Count total changes
            total_changes = sum(
                file_change.changes.total if file_change.changes else 0
                for file_change in files
            )

            # Create summary
            summary = DirectorySummary(
                path=directory,
                file_count=len(files),
                total_changes=total_changes,
                extensions=extensions,
            )

            summaries.append(summary)

        return summaries
