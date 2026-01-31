"""
agmem add - Add files to the staging area with file type validation.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.repository import Repository


# Default allowed file extensions for memory files
DEFAULT_ALLOWED_EXTENSIONS = {'.md', '.txt', '.json', '.yaml', '.yml'}

# Binary file signatures (magic bytes) to detect binary files
BINARY_SIGNATURES = [
    b'\x89PNG',      # PNG
    b'\xff\xd8\xff', # JPEG
    b'GIF8',         # GIF
    b'%PDF',         # PDF
    b'PK\x03\x04',   # ZIP
    b'\x1f\x8b',     # GZIP
    b'BM',           # BMP
    b'\x00\x00\x01\x00',  # ICO
    b'RIFF',         # WAV, AVI, etc.
]


class AddCommand:
    """Add files to the staging area."""
    
    name = 'add'
    help = 'Add memory files to staging area'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            'paths',
            nargs='+',
            help='Files or directories to stage'
        )
        parser.add_argument(
            '--all', '-A',
            action='store_true',
            help='Stage all changes (including modifications and deletions)'
        )
        parser.add_argument(
            '--force', '-f',
            action='store_true',
            help='Force add even if file type is not recommended'
        )
        parser.add_argument(
            '--allow-binary',
            action='store_true',
            help='Allow staging binary files (not recommended)'
        )
    
    @staticmethod
    def _is_binary_file(filepath: Path) -> bool:
        """Check if a file is binary by looking at magic bytes."""
        try:
            with open(filepath, 'rb') as f:
                header = f.read(16)
            
            for signature in BINARY_SIGNATURES:
                if header.startswith(signature):
                    return True
            
            # Also check for null bytes (common in binary files)
            if b'\x00' in header:
                return True
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def _is_allowed_extension(filepath: Path, config: dict) -> bool:
        """Check if file extension is in allowed list."""
        allowed = config.get('allowed_extensions', list(DEFAULT_ALLOWED_EXTENSIONS))
        allowed_set = set(allowed)
        
        ext = filepath.suffix.lower()
        return ext in allowed_set or not ext  # Allow files without extension
    
    @staticmethod
    def _validate_file(filepath: Path, config: dict, force: bool, allow_binary: bool) -> tuple:
        """
        Validate a file for staging.
        
        Returns:
            Tuple of (is_valid, warning_message)
        """
        # Check for binary files
        if AddCommand._is_binary_file(filepath):
            if allow_binary:
                return True, f"Warning: {filepath} appears to be binary"
            else:
                return False, f"Rejected: {filepath} is a binary file. Use --allow-binary to override."
        
        # Check extension
        if not AddCommand._is_allowed_extension(filepath, config):
            ext = filepath.suffix or '(no extension)'
            allowed = config.get('allowed_extensions', list(DEFAULT_ALLOWED_EXTENSIONS))
            
            if force:
                return True, f"Warning: {filepath} has extension '{ext}' which may not be optimal"
            else:
                return False, (
                    f"Rejected: {filepath} has extension '{ext}'.\n"
                    f"  Recommended: {', '.join(sorted(allowed))}\n"
                    f"  Use --force to override."
                )
        
        return True, None
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        staged_count = 0
        rejected_count = 0
        config = repo.get_config()
        
        for path_str in args.paths:
            path = Path(path_str)
            
            # Handle '.' to stage all
            if path_str == '.':
                staged, rejected = AddCommand._stage_directory_with_validation(
                    repo, None, config, args.force, args.allow_binary
                )
                staged_count += staged
                rejected_count += rejected
                continue
            
            # Resolve path relative to current/
            if path.is_absolute():
                try:
                    rel_path = path.relative_to(repo.current_dir)
                except ValueError:
                    print(f"Error: Path {path} is outside repository")
                    continue
            else:
                # Check if it's in current/ or needs to be resolved
                if (repo.current_dir / path).exists():
                    rel_path = path
                elif path.exists():
                    # Path exists outside current/, copy it in
                    target = repo.current_dir / path.name
                    if path.is_file():
                        target.write_bytes(path.read_bytes())
                    rel_path = Path(path.name)
                else:
                    print(f"Error: Path not found: {path}")
                    continue
            
            full_path = repo.current_dir / rel_path
            
            if not full_path.exists():
                print(f"Error: Path not found: {path}")
                continue
            
            if full_path.is_file():
                # Validate file
                is_valid, message = AddCommand._validate_file(
                    full_path, config, args.force, args.allow_binary
                )
                
                if not is_valid:
                    print(message)
                    rejected_count += 1
                    continue
                
                if message:  # Warning
                    print(message)
                
                try:
                    blob_hash = repo.stage_file(str(rel_path))
                    print(f"  staged: {rel_path}")
                    staged_count += 1
                except Exception as e:
                    print(f"Error staging {rel_path}: {e}")
            
            elif full_path.is_dir():
                staged, rejected = AddCommand._stage_directory_with_validation(
                    repo, str(rel_path), config, args.force, args.allow_binary
                )
                staged_count += staged
                rejected_count += rejected
        
        if staged_count > 0 or rejected_count > 0:
            print(f"\nStaged {staged_count} file(s)")
            if rejected_count > 0:
                print(f"Rejected {rejected_count} file(s) - use --force to override")
            if staged_count > 0:
                print("Run 'agmem commit -m \"message\"' to save snapshot")
        else:
            print("No files staged")
        
        return 0
    
    @staticmethod
    def _stage_directory_with_validation(repo, subdir: str, config: dict, force: bool, allow_binary: bool) -> tuple:
        """
        Stage a directory with file validation.
        
        Returns:
            Tuple of (staged_count, rejected_count)
        """
        staged_count = 0
        rejected_count = 0
        
        if subdir:
            dir_path = repo.current_dir / subdir
        else:
            dir_path = repo.current_dir
        
        if not dir_path.exists():
            return 0, 0
        
        for file_path in dir_path.rglob('*'):
            if not file_path.is_file():
                continue
            
            # Skip hidden files and .mem directory
            rel_to_current = file_path.relative_to(repo.current_dir)
            if any(part.startswith('.') for part in rel_to_current.parts):
                continue
            
            # Validate file
            is_valid, message = AddCommand._validate_file(
                file_path, config, force, allow_binary
            )
            
            if not is_valid:
                if not force:
                    # Only print first few rejections to avoid spam
                    if rejected_count < 5:
                        print(f"  {message}")
                    elif rejected_count == 5:
                        print("  ... (more files rejected)")
                rejected_count += 1
                continue
            
            if message:  # Warning
                print(message)
            
            try:
                repo.stage_file(str(rel_to_current))
                print(f"  staged: {rel_to_current}")
                staged_count += 1
            except Exception as e:
                print(f"Error staging {rel_to_current}: {e}")
        
        return staged_count, rejected_count
