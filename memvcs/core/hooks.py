"""
Pre-commit hooks for agmem.

Provides hook infrastructure for validation before commits.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Optional
from pathlib import Path


@dataclass
class HookResult:
    """Result of running hooks."""
    success: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, message: str):
        """Add an error and mark as failed."""
        self.errors.append(message)
        self.success = False
    
    def add_warning(self, message: str):
        """Add a warning (doesn't affect success)."""
        self.warnings.append(message)


def run_pre_commit_hooks(repo, staged_files: Dict[str, Any]) -> HookResult:
    """
    Run all pre-commit hooks on staged files.
    
    Args:
        repo: Repository instance
        staged_files: Dict of staged files with their info
        
    Returns:
        HookResult with success status and any errors/warnings
    """
    result = HookResult(success=True)
    
    # Run PII scanner hook
    try:
        from .pii_scanner import PIIScanner
        pii_result = PIIScanner.scan_staged_files(repo, staged_files)
        
        if pii_result.has_issues:
            for issue in pii_result.issues:
                result.add_error(f"PII detected in {issue.filepath}: {issue.description}")
    except ImportError:
        # PII scanner not available, skip
        pass
    except Exception as e:
        result.add_warning(f"PII scanner failed: {e}")
    
    # Run file type validation hook
    file_type_result = validate_file_types(repo, staged_files)
    if not file_type_result.success:
        for error in file_type_result.errors:
            result.add_error(error)
    for warning in file_type_result.warnings:
        result.add_warning(warning)
    
    return result


def validate_file_types(repo, staged_files: Dict[str, Any]) -> HookResult:
    """
    Validate that staged files are allowed types.
    
    Args:
        repo: Repository instance
        staged_files: Dict of staged files
        
    Returns:
        HookResult with validation status
    """
    result = HookResult(success=True)
    
    # Get config for allowed extensions
    config = repo.get_config()
    allowed_extensions = config.get('allowed_extensions', ['.md', '.txt', '.json', '.yaml', '.yml'])
    
    for filepath in staged_files.keys():
        path = Path(filepath)
        ext = path.suffix.lower()
        
        # Skip files without extensions (might be valid)
        if not ext:
            continue
        
        # Check if extension is allowed
        if ext not in allowed_extensions:
            result.add_warning(
                f"File '{filepath}' has extension '{ext}' which may not be optimal for memory storage. "
                f"Recommended: {', '.join(allowed_extensions)}"
            )
    
    return result


# Hook registry for custom hooks
_registered_hooks: List[Callable] = []


def register_hook(hook_fn: Callable):
    """
    Register a custom pre-commit hook.
    
    Args:
        hook_fn: Function that takes (repo, staged_files) and returns HookResult
    """
    _registered_hooks.append(hook_fn)


def get_registered_hooks() -> List[Callable]:
    """Get all registered hooks."""
    return _registered_hooks.copy()
