"""Helper utility functions."""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional


def find_repo_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find the repository root by looking for .mem directory.
    
    Args:
        start_path: Path to start searching from (default: current directory)
        
    Returns:
        Path to repository root or None if not found
    """
    if start_path is None:
        start_path = Path('.').resolve()
    
    current = start_path
    
    while current != current.parent:
        if (current / '.mem').exists():
            return current
        current = current.parent
    
    return None


def format_timestamp(timestamp_str: str, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Format an ISO timestamp string.
    
    Args:
        timestamp_str: ISO format timestamp
        format_str: Output format string
        
    Returns:
        Formatted timestamp string
    """
    try:
        # Handle 'Z' suffix
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1]
        
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime(format_str)
    except (ValueError, TypeError):
        return timestamp_str


def shorten_hash(hash_id: str, length: int = 8) -> str:
    """
    Shorten a hash for display.
    
    Args:
        hash_id: Full hash string
        length: Length of shortened hash
        
    Returns:
        Shortened hash
    """
    if len(hash_id) <= length:
        return hash_id
    return hash_id[:length]


def human_readable_size(size_bytes: int) -> str:
    """
    Convert bytes to human readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human readable string (e.g., "1.5 MB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.1f} GB"


def parse_memory_type(filepath: str) -> str:
    """
    Parse memory type from file path.
    
    Args:
        filepath: Path to memory file
        
    Returns:
        Memory type ('episodic', 'semantic', 'procedural', 'unknown')
    """
    path_lower = filepath.lower()
    
    if 'episodic' in path_lower:
        return 'episodic'
    elif 'semantic' in path_lower:
        return 'semantic'
    elif 'procedural' in path_lower or 'workflow' in path_lower:
        return 'procedural'
    elif 'checkpoint' in path_lower:
        return 'checkpoint'
    elif 'summary' in path_lower:
        return 'summary'
    
    return 'unknown'


def is_binary_content(content: bytes) -> bool:
    """
    Check if content appears to be binary.
    
    Args:
        content: Content bytes to check
        
    Returns:
        True if content appears binary
    """
    # Check for null bytes
    if b'\x00' in content:
        return True
    
    # Check for high ratio of non-printable characters
    if len(content) == 0:
        return False
    
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})
    non_text = sum(1 for byte in content if byte not in text_chars)
    
    return non_text / len(content) > 0.30


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe use.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing whitespace and dots
    filename = filename.strip(' .')
    
    # Ensure not empty
    if not filename:
        filename = 'unnamed'
    
    return filename


def generate_session_id() -> str:
    """
    Generate a unique session ID.
    
    Returns:
        Session ID string
    """
    from datetime import datetime
    import uuid
    
    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    short_uuid = str(uuid.uuid4())[:8]
    
    return f"session-{timestamp}-{short_uuid}"
