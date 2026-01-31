"""
PII (Personally Identifiable Information) scanner for agmem.

Scans staged files for sensitive information before commit.
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PIIIssue:
    """A detected PII issue."""
    filepath: str
    line_number: int
    issue_type: str
    description: str
    matched_text: str  # Partially redacted
    severity: str = "high"  # "high", "medium", "low"


@dataclass
class PIIScanResult:
    """Result of scanning for PII."""
    has_issues: bool
    issues: List[PIIIssue] = field(default_factory=list)
    scanned_files: int = 0
    
    def add_issue(self, issue: PIIIssue):
        self.issues.append(issue)
        self.has_issues = True


class PIIScanner:
    """
    Scanner for detecting PII and secrets in memory files.
    
    Detects:
    - API keys and tokens
    - Credit card numbers
    - Email addresses
    - Social Security Numbers
    - Phone numbers
    - IP addresses
    - Private keys
    - Database connection strings
    """
    
    # Patterns for detecting various types of PII and secrets
    PATTERNS = {
        'api_key': {
            'pattern': re.compile(
                r'(?i)'
                r'(?:api[_-]?key|apikey|api[_-]?secret|api[_-]?token|'
                r'auth[_-]?token|access[_-]?token|bearer[_-]?token|'
                r'secret[_-]?key|private[_-]?key|password|passwd|pwd)'
                r'\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{16,})["\']?',
                re.MULTILINE
            ),
            'description': 'API key or secret token detected',
            'severity': 'high'
        },
        'aws_key': {
            'pattern': re.compile(r'(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}'),
            'description': 'AWS access key detected',
            'severity': 'high'
        },
        'aws_secret': {
            'pattern': re.compile(
                r'(?i)aws[_-]?secret[_-]?(?:access[_-]?)?key\s*[:=]\s*["\']?([a-zA-Z0-9+/]{40})["\']?'
            ),
            'description': 'AWS secret access key detected',
            'severity': 'high'
        },
        'private_key': {
            'pattern': re.compile(
                r'-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----'
            ),
            'description': 'Private key detected',
            'severity': 'high'
        },
        'credit_card': {
            'pattern': re.compile(
                r'\b(?:4[0-9]{12}(?:[0-9]{3})?|'  # Visa
                r'5[1-5][0-9]{14}|'               # Mastercard
                r'3[47][0-9]{13}|'                # Amex
                r'6(?:011|5[0-9]{2})[0-9]{12})\b' # Discover
            ),
            'description': 'Credit card number detected',
            'severity': 'high'
        },
        'ssn': {
            'pattern': re.compile(r'\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b'),
            'description': 'Social Security Number detected',
            'severity': 'high'
        },
        'email': {
            'pattern': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            'description': 'Email address detected',
            'severity': 'medium'
        },
        'phone': {
            'pattern': re.compile(
                r'\b(?:\+?1[-.\s]?)?\(?[2-9][0-9]{2}\)?[-.\s]?[2-9][0-9]{2}[-.\s]?[0-9]{4}\b'
            ),
            'description': 'Phone number detected',
            'severity': 'medium'
        },
        'ip_address': {
            'pattern': re.compile(
                r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
                r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
            ),
            'description': 'IP address detected',
            'severity': 'low'
        },
        'database_url': {
            'pattern': re.compile(
                r'(?i)(?:postgres|mysql|mongodb|redis)://[^\s"\'"]+',
                re.MULTILINE
            ),
            'description': 'Database connection string detected',
            'severity': 'high'
        },
        'jwt': {
            'pattern': re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'),
            'description': 'JWT token detected',
            'severity': 'high'
        },
        'github_token': {
            'pattern': re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}'),
            'description': 'GitHub token detected',
            'severity': 'high'
        },
        'slack_token': {
            'pattern': re.compile(r'xox[baprs]-[0-9]+-[0-9]+-[a-zA-Z0-9]+'),
            'description': 'Slack token detected',
            'severity': 'high'
        },
        'stripe_key': {
            'pattern': re.compile(r'(?:sk|pk)_(?:test|live)_[a-zA-Z0-9]{24,}'),
            'description': 'Stripe API key detected',
            'severity': 'high'
        }
    }
    
    # Files/patterns to skip
    SKIP_PATTERNS = [
        r'\.git/',
        r'\.mem/',
        r'node_modules/',
        r'__pycache__/',
        r'\.pyc$',
        r'\.pyo$',
    ]
    
    @classmethod
    def _redact(cls, text: str, keep: int = 4) -> str:
        """Partially redact sensitive text for display."""
        if len(text) <= keep * 2:
            return '*' * len(text)
        return text[:keep] + '*' * (len(text) - keep * 2) + text[-keep:]
    
    @classmethod
    def _should_skip(cls, filepath: str) -> bool:
        """Check if file should be skipped."""
        for pattern in cls.SKIP_PATTERNS:
            if re.search(pattern, filepath):
                return True
        return False
    
    @classmethod
    def scan_content(cls, content: str, filepath: str) -> List[PIIIssue]:
        """
        Scan content for PII.
        
        Args:
            content: File content to scan
            filepath: Path to the file (for reporting)
            
        Returns:
            List of PIIIssue objects
        """
        issues = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            for pii_type, config in cls.PATTERNS.items():
                matches = config['pattern'].finditer(line)
                for match in matches:
                    matched_text = match.group(0)
                    
                    # Skip common false positives
                    if cls._is_false_positive(pii_type, matched_text, line):
                        continue
                    
                    issues.append(PIIIssue(
                        filepath=filepath,
                        line_number=line_num,
                        issue_type=pii_type,
                        description=config['description'],
                        matched_text=cls._redact(matched_text),
                        severity=config['severity']
                    ))
        
        return issues
    
    @classmethod
    def _is_false_positive(cls, pii_type: str, matched_text: str, line: str) -> bool:
        """Check for common false positives."""
        lower_line = line.lower()
        
        # Skip example/placeholder values
        if any(x in lower_line for x in ['example', 'placeholder', 'your_', 'xxx', 'sample']):
            return True
        
        # Skip comments that are likely documentation
        if line.strip().startswith('#') and 'example' in lower_line:
            return True
        
        # IP address false positives
        if pii_type == 'ip_address':
            # Skip localhost and common internal IPs
            if matched_text in ['127.0.0.1', '0.0.0.0', '192.168.0.1', '10.0.0.1']:
                return True
            # Skip version numbers that look like IPs
            if 'version' in lower_line or 'v.' in lower_line:
                return True
        
        # Email false positives
        if pii_type == 'email':
            # Skip example domains
            if any(x in matched_text for x in ['example.com', 'test.com', 'localhost']):
                return True
        
        return False
    
    @classmethod
    def scan_file(cls, filepath: Path) -> List[PIIIssue]:
        """
        Scan a file for PII.
        
        Args:
            filepath: Path to the file
            
        Returns:
            List of PIIIssue objects
        """
        if cls._should_skip(str(filepath)):
            return []
        
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            return cls.scan_content(content, str(filepath))
        except Exception:
            return []
    
    @classmethod
    def _get_blob_hash_from_staged(cls, file_info: Any) -> Optional[str]:
        """Get blob hash from StagedFile or dict (staging returns Dict[str, StagedFile])."""
        if hasattr(file_info, 'blob_hash'):
            return file_info.blob_hash
        if isinstance(file_info, dict):
            return file_info.get('blob_hash') or file_info.get('hash')
        return None

    @classmethod
    def scan_staged_files(cls, repo, staged_files: Dict[str, Any]) -> PIIScanResult:
        """
        Scan staged files for PII.
        
        Args:
            repo: Repository instance
            staged_files: Dict of staged files with their info
            
        Returns:
            PIIScanResult with any issues found
        """
        from .objects import Blob
        
        result = PIIScanResult(has_issues=False)
        
        for filepath, file_info in staged_files.items():
            if cls._should_skip(filepath):
                continue
            
            result.scanned_files += 1
            
            blob_hash = PIIScanner._get_blob_hash_from_staged(file_info)
            if not blob_hash:
                continue
            
            blob = Blob.load(repo.object_store, blob_hash)
            if not blob:
                continue
            
            try:
                content = blob.content.decode('utf-8', errors='ignore')
            except Exception:
                continue
            
            # Scan content
            issues = cls.scan_content(content, filepath)
            for issue in issues:
                result.add_issue(issue)
        
        return result
    
    @classmethod
    def scan_directory(cls, directory: Path, recursive: bool = True) -> PIIScanResult:
        """
        Scan a directory for PII.
        
        Args:
            directory: Directory to scan
            recursive: Whether to scan recursively
            
        Returns:
            PIIScanResult with any issues found
        """
        result = PIIScanResult(has_issues=False)
        
        if recursive:
            files = directory.rglob('*')
        else:
            files = directory.glob('*')
        
        for filepath in files:
            if not filepath.is_file():
                continue
            
            if cls._should_skip(str(filepath)):
                continue
            
            result.scanned_files += 1
            issues = cls.scan_file(filepath)
            for issue in issues:
                result.add_issue(issue)
        
        return result
