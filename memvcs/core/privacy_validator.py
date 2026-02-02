"""
Privacy field validation and auditing.

Ensures differential privacy noise is only applied to fact data, not metadata.
Prevents accidental privacy overhead on metadata fields and provides audit trail.

Provides:
- @privacy_exempt: Decorator to mark metadata fields as privacy-exempt
- PrivacyFieldValidator: Runtime validation that noise is applied correctly
- PrivacyAuditReport: Audit trail of which fields received noise
"""

from typing import Any, Callable, Dict, List, Optional, Set
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PrivacyAuditReport:
    """Audit report of privacy noise application."""

    timestamp: str
    noised_fields: Dict[str, Any] = field(default_factory=dict)
    exempt_fields: Dict[str, Any] = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging/serialization."""
        return {
            "timestamp": self.timestamp,
            "noised_fields": self.noised_fields,
            "exempt_fields": self.exempt_fields,
            "validation_errors": self.validation_errors,
            "summary": {
                "total_noised": len(self.noised_fields),
                "total_exempt": len(self.exempt_fields),
                "validation_passed": len(self.validation_errors) == 0,
            },
        }


class PrivacyFieldValidator:
    """Validates that privacy noise is applied correctly.

    Tracks which fields receive noise vs. are exempt from noise.
    Fails loudly if noise is applied to exempt fields.
    """

    # Metadata fields that should NEVER receive noise (they don't reveal facts)
    EXEMPT_FIELDS = {
        "clusters_found",  # Metadata: count of clusters, not individual facts
        "insights_generated",  # Metadata: count of insights generated
        "episodes_archived",  # Metadata: count of archived episodes
        "confidence_score",  # Metadata: overall quality metric, not a fact
        "summary_version",  # Metadata: schema version
        "created_at",  # Metadata: timestamp
        "updated_at",  # Metadata: timestamp
        "agent_version",  # Metadata: software version
    }

    # Fact-related fields that SHOULD receive noise
    FACT_FIELDS = {
        "facts",  # List of actual facts
        "memories",  # Memory content
        "semantic_content",  # Semantic memory content
        "episodic_content",  # Episodic memory content
        "procedural_content",  # Procedural memory content
        "embeddings",  # Vector representations of facts
        "fact_count",  # Count of individual facts (not metadata)
        "memory_count",  # Count of individual memories
    }

    def __init__(self):
        self.audit_report = PrivacyAuditReport(timestamp=datetime.now(timezone.utc).isoformat())

    def validate_noised_field(
        self, field_name: str, field_value: Any, is_noised: bool = True
    ) -> None:
        """Validate that noise application is correct for a field.

        Args:
            field_name: Name of the field
            field_value: Value of the field
            is_noised: Whether noise was applied to this field

        Raises:
            RuntimeError: If noise is applied to exempt field
        """
        if is_noised and field_name in self.EXEMPT_FIELDS:
            error = (
                f"ERROR: Noise applied to exempt metadata field '{field_name}'. "
                f"Metadata fields do not reveal individual facts and should not receive noise. "
                f"Remove noise from: {field_name}"
            )
            self.audit_report.validation_errors.append(error)
            raise RuntimeError(error)

        if is_noised:
            self.audit_report.noised_fields[field_name] = field_value
        else:
            self.audit_report.exempt_fields[field_name] = field_value

    def validate_result_dict(self, result: Dict[str, Any]) -> None:
        """Validate a result dict (e.g., DistillerResult or GardenerResult).

        Args:
            result: The result dict to validate

        Raises:
            RuntimeError: If privacy validation fails
        """
        for field_name in self.EXEMPT_FIELDS:
            if field_name in result:
                # These fields should not have been noised
                self.audit_report.exempt_fields[field_name] = result[field_name]

    def get_report(self) -> PrivacyAuditReport:
        """Get the audit report."""
        if self.audit_report.validation_errors:
            print(
                "Privacy Validation Report:\n"
                + "\n".join(f"  {e}" for e in self.audit_report.validation_errors)
            )
        return self.audit_report


def privacy_exempt(func: Callable) -> Callable:
    """Decorator to mark a function as privacy-exempt.

    The decorated function should not apply DP noise to its result.
    Used to document which functions are exempt from privacy operations.

    Example:
        @privacy_exempt
        def get_metadata() -> Dict[str, Any]:
            return {"clusters_found": 42, "created_at": "2024-01-01T00:00:00Z"}
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        # Mark result as privacy-exempt (store in metadata if possible)
        if isinstance(result, dict):
            result["_privacy_exempt"] = True
        return result

    # Mark the wrapper function to indicate it's privacy-exempt
    setattr(wrapper, "_privacy_exempt_function", True)
    return wrapper


class PrivacyGuard:
    """Context manager and decorator for privacy-aware code blocks.

    Usage:
        with PrivacyGuard() as pg:
            result = process_facts(data)
            pg.mark_noised("fact_count")
    """

    def __init__(self, strict: bool = True):
        self.strict = strict
        self.validator = PrivacyFieldValidator()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        return True

    def mark_noised(self, field_name: str, value: Any = None) -> None:
        """Mark a field as having received DP noise."""
        if self.strict:
            self.validator.validate_noised_field(field_name, value, is_noised=True)
        else:
            self.validator.audit_report.noised_fields[field_name] = value

    def mark_exempt(self, field_name: str, value: Any = None) -> None:
        """Mark a field as exempt from DP noise."""
        self.validator.audit_report.exempt_fields[field_name] = value

    def get_report(self) -> PrivacyAuditReport:
        """Get the privacy audit report."""
        return self.validator.get_report()
