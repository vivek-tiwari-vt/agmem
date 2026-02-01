"""
Schema validation for agmem memory files.

Implements YAML frontmatter parsing and validation for structured memory metadata.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .constants import MEMORY_TYPES


class MemoryType(Enum):
    """Memory types with their validation requirements."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    CHECKPOINTS = "checkpoints"
    SESSION_SUMMARIES = "session-summaries"
    UNKNOWN = "unknown"


@dataclass
class FrontmatterData:
    """Parsed frontmatter data from a memory file."""

    schema_version: str = "1.0"
    last_updated: Optional[str] = None
    source_agent_id: Optional[str] = None
    confidence_score: Optional[float] = None
    memory_type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    importance: Optional[float] = None  # 0.0-1.0 for recall/decay weighting
    valid_from: Optional[str] = None  # ISO 8601 for epistemic versioning
    valid_until: Optional[str] = None  # ISO 8601 for epistemic versioning
    source_authority: Optional[str] = None  # "human-provided" or "inferred"
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "schema_version": self.schema_version,
        }
        if self.last_updated:
            result["last_updated"] = self.last_updated
        if self.source_agent_id:
            result["source_agent_id"] = self.source_agent_id
        if self.confidence_score is not None:
            result["confidence_score"] = self.confidence_score
        if self.memory_type:
            result["memory_type"] = self.memory_type
        if self.tags:
            result["tags"] = self.tags
        if self.importance is not None:
            result["importance"] = self.importance
        if self.valid_from:
            result["valid_from"] = self.valid_from
        if self.valid_until:
            result["valid_until"] = self.valid_until
        if self.source_authority:
            result["source_authority"] = self.source_authority
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FrontmatterData":
        """Create from dictionary."""
        known_fields = {
            "schema_version",
            "last_updated",
            "source_agent_id",
            "confidence_score",
            "memory_type",
            "tags",
            "importance",
            "valid_from",
            "valid_until",
            "source_authority",
        }
        extra = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            schema_version=data.get("schema_version", "1.0"),
            last_updated=data.get("last_updated"),
            source_agent_id=data.get("source_agent_id"),
            confidence_score=data.get("confidence_score"),
            memory_type=data.get("memory_type"),
            tags=data.get("tags", []),
            importance=data.get("importance"),
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
            source_authority=data.get("source_authority"),
            extra=extra,
        )


@dataclass
class ValidationError:
    """A single validation error."""

    field: str
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationResult:
    """Result of validating a memory file."""

    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    frontmatter: Optional[FrontmatterData] = None

    def add_error(self, field: str, message: str):
        """Add a validation error."""
        self.errors.append(ValidationError(field=field, message=message, severity="error"))
        self.valid = False

    def add_warning(self, field: str, message: str):
        """Add a validation warning."""
        self.warnings.append(ValidationError(field=field, message=message, severity="warning"))


class FrontmatterParser:
    """Parser for YAML frontmatter in memory files."""

    # Regex to match YAML frontmatter block
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL | re.MULTILINE)

    @classmethod
    def parse(cls, content: str) -> Tuple[Optional[FrontmatterData], str]:
        """
        Parse frontmatter from content.

        Args:
            content: Full file content

        Returns:
            Tuple of (frontmatter_data, body_content)
            frontmatter_data is None if no frontmatter found
        """
        if not YAML_AVAILABLE:
            # Without PyYAML, return None for frontmatter
            return None, content

        match = cls.FRONTMATTER_PATTERN.match(content)
        if not match:
            return None, content

        yaml_content = match.group(1)
        body = content[match.end() :]

        try:
            data = yaml.safe_load(yaml_content)
            if not isinstance(data, dict):
                return None, content

            frontmatter = FrontmatterData.from_dict(data)
            return frontmatter, body
        except yaml.YAMLError:
            return None, content

    @classmethod
    def has_frontmatter(cls, content: str) -> bool:
        """Check if content has YAML frontmatter."""
        return bool(cls.FRONTMATTER_PATTERN.match(content))

    @classmethod
    def create_frontmatter(cls, data: FrontmatterData) -> str:
        """
        Create YAML frontmatter string from data.

        Args:
            data: FrontmatterData to serialize

        Returns:
            YAML frontmatter string with delimiters
        """
        if not YAML_AVAILABLE:
            # Manual YAML generation without PyYAML
            lines = ["---"]
            d = data.to_dict()
            for key, value in d.items():
                if isinstance(value, list):
                    lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
                elif value is not None:
                    lines.append(f"{key}: {value}")
            lines.append("---")
            return "\n".join(lines) + "\n"

        yaml_str = yaml.dump(data.to_dict(), default_flow_style=False, sort_keys=False)
        return f"---\n{yaml_str}---\n"

    @classmethod
    def add_or_update_frontmatter(cls, content: str, data: FrontmatterData) -> str:
        """
        Add or update frontmatter in content.

        Args:
            content: Original file content
            data: FrontmatterData to add/update

        Returns:
            Content with updated frontmatter
        """
        _, body = cls.parse(content)
        frontmatter_str = cls.create_frontmatter(data)
        return frontmatter_str + body


class SchemaValidator:
    """Validates memory files against schema requirements."""

    # Required fields per memory type
    REQUIRED_FIELDS: Dict[MemoryType, List[str]] = {
        MemoryType.SEMANTIC: ["schema_version", "last_updated"],
        MemoryType.EPISODIC: ["schema_version"],
        MemoryType.PROCEDURAL: ["schema_version", "last_updated"],
        MemoryType.CHECKPOINTS: ["schema_version", "last_updated"],
        MemoryType.SESSION_SUMMARIES: ["schema_version", "last_updated"],
        MemoryType.UNKNOWN: ["schema_version"],
    }

    # Recommended fields per memory type (generate warnings if missing)
    RECOMMENDED_FIELDS: Dict[MemoryType, List[str]] = {
        MemoryType.SEMANTIC: ["source_agent_id", "confidence_score", "tags"],
        MemoryType.EPISODIC: ["source_agent_id"],
        MemoryType.PROCEDURAL: ["source_agent_id", "tags"],
        MemoryType.CHECKPOINTS: ["source_agent_id"],
        MemoryType.SESSION_SUMMARIES: ["source_agent_id"],
        MemoryType.UNKNOWN: [],
    }

    @classmethod
    def detect_memory_type(cls, filepath: str) -> MemoryType:
        """
        Detect memory type from file path.

        Args:
            filepath: Path to the file

        Returns:
            MemoryType enum value
        """
        path_lower = filepath.lower()

        if "episodic" in path_lower:
            return MemoryType.EPISODIC
        elif "semantic" in path_lower:
            return MemoryType.SEMANTIC
        elif "procedural" in path_lower:
            return MemoryType.PROCEDURAL
        elif "checkpoint" in path_lower:
            return MemoryType.CHECKPOINTS
        elif "session-summar" in path_lower or "session_summar" in path_lower:
            return MemoryType.SESSION_SUMMARIES

        return MemoryType.UNKNOWN

    @classmethod
    def validate(cls, content: str, filepath: str, strict: bool = False) -> ValidationResult:
        """
        Validate a memory file's frontmatter.

        Args:
            content: File content
            filepath: Path to the file (for type detection)
            strict: If True, treat warnings as errors

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(valid=True)
        memory_type = cls.detect_memory_type(filepath)

        # Parse frontmatter
        frontmatter, body = FrontmatterParser.parse(content)
        result.frontmatter = frontmatter

        # Check for missing frontmatter
        if frontmatter is None:
            result.add_error("frontmatter", "Missing YAML frontmatter block")
            return result

        # Check required fields
        required = cls.REQUIRED_FIELDS.get(memory_type, [])
        frontmatter_dict = frontmatter.to_dict()

        for field in required:
            if field not in frontmatter_dict or frontmatter_dict[field] is None:
                result.add_error(field, f"Required field '{field}' is missing")

        # Check recommended fields
        recommended = cls.RECOMMENDED_FIELDS.get(memory_type, [])
        for field in recommended:
            if field not in frontmatter_dict or frontmatter_dict[field] is None:
                if strict:
                    result.add_error(field, f"Recommended field '{field}' is missing (strict mode)")
                else:
                    result.add_warning(field, f"Recommended field '{field}' is missing")

        # Validate schema_version format
        if frontmatter.schema_version:
            if not re.match(r"^\d+\.\d+$", frontmatter.schema_version):
                result.add_error(
                    "schema_version",
                    f"Invalid schema_version format: '{frontmatter.schema_version}' (expected X.Y)",
                )

        # Validate last_updated format (ISO 8601)
        if frontmatter.last_updated:
            try:
                # Try parsing ISO format
                if frontmatter.last_updated.endswith("Z"):
                    datetime.fromisoformat(frontmatter.last_updated.replace("Z", "+00:00"))
                else:
                    datetime.fromisoformat(frontmatter.last_updated)
            except ValueError:
                result.add_error(
                    "last_updated",
                    f"Invalid last_updated format: '{frontmatter.last_updated}' (expected ISO 8601)",
                )

        # Validate confidence_score range
        if frontmatter.confidence_score is not None:
            if not isinstance(frontmatter.confidence_score, (int, float)):
                result.add_error(
                    "confidence_score",
                    f"confidence_score must be a number, got: {type(frontmatter.confidence_score).__name__}",
                )
            elif not (0.0 <= frontmatter.confidence_score <= 1.0):
                result.add_error(
                    "confidence_score",
                    f"confidence_score must be between 0.0 and 1.0, got: {frontmatter.confidence_score}",
                )

        # Validate memory_type if specified
        if frontmatter.memory_type:
            valid_types = [mt.value for mt in MemoryType if mt != MemoryType.UNKNOWN]
            if frontmatter.memory_type not in valid_types:
                result.add_warning(
                    "memory_type",
                    f"Unknown memory_type: '{frontmatter.memory_type}' (expected one of: {valid_types})",
                )

        # Validate tags is a list
        if frontmatter.tags and not isinstance(frontmatter.tags, list):
            result.add_error("tags", f"tags must be a list, got: {type(frontmatter.tags).__name__}")

        return result

    @classmethod
    def validate_batch(
        cls, files: Dict[str, str], strict: bool = False
    ) -> Dict[str, ValidationResult]:
        """
        Validate multiple files.

        Args:
            files: Dict mapping filepath to content
            strict: If True, treat warnings as errors

        Returns:
            Dict mapping filepath to ValidationResult
        """
        results = {}
        for filepath, content in files.items():
            results[filepath] = cls.validate(content, filepath, strict)
        return results


def generate_frontmatter(
    memory_type: str = "semantic",
    source_agent_id: Optional[str] = None,
    confidence_score: Optional[float] = None,
    tags: Optional[List[str]] = None,
) -> FrontmatterData:
    """
    Generate frontmatter data with current timestamp.

    Args:
        memory_type: Type of memory (episodic, semantic, procedural, etc.)
        source_agent_id: ID of the agent creating this memory
        confidence_score: Confidence score (0.0 to 1.0)
        tags: List of tags for categorization

    Returns:
        FrontmatterData with populated fields
    """
    return FrontmatterData(
        schema_version="1.0",
        last_updated=datetime.utcnow().isoformat() + "Z",
        source_agent_id=source_agent_id,
        confidence_score=confidence_score,
        memory_type=memory_type,
        tags=tags or [],
    )


def compare_timestamps(timestamp1: Optional[str], timestamp2: Optional[str]) -> int:
    """
    Compare two ISO 8601 timestamps.

    Args:
        timestamp1: First timestamp
        timestamp2: Second timestamp

    Returns:
        -1 if timestamp1 < timestamp2
         0 if timestamp1 == timestamp2
         1 if timestamp1 > timestamp2

    If either timestamp is None or invalid, the other is considered newer.
    """

    def parse_ts(ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            if ts.endswith("Z"):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    dt1 = parse_ts(timestamp1)
    dt2 = parse_ts(timestamp2)

    if dt1 is None and dt2 is None:
        return 0
    if dt1 is None:
        return -1
    if dt2 is None:
        return 1

    if dt1 < dt2:
        return -1
    elif dt1 > dt2:
        return 1
    return 0
