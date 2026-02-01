"""
Consistency checker - belief consistency for agmem semantic memories.

Extracts (subject, predicate, object) triples and detects logical contradictions.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from .constants import MEMORY_TYPES
from .schema import FrontmatterParser


@dataclass
class Triple:
    """A (subject, predicate, object) triple."""

    subject: str
    predicate: str
    obj: str
    confidence: float
    source: str
    line: int


@dataclass
class Contradiction:
    """A detected contradiction."""

    triple1: Triple
    triple2: Triple
    reason: str


@dataclass
class ConsistencyResult:
    """Result of consistency check."""

    valid: bool
    contradictions: List[Contradiction] = field(default_factory=list)
    triples: List[Triple] = field(default_factory=list)
    files_checked: int = 0


# Inverse predicate pairs (A likes B vs B disliked by A)
INVERSE_PREDICATES = [
    ("likes", "dislikes"),
    ("prefers", "avoids"),
    ("uses", "avoids"),
    ("enables", "disables"),
    ("true", "false"),
]


class ConsistencyChecker:
    """Detects logical contradictions in semantic memories."""

    def __init__(self, repo: Any, llm_provider: Optional[str] = None):
        self.repo = repo
        self.llm_provider = llm_provider
        self.current_dir = repo.root / "current"

    def _extract_triples_simple(self, content: str, source: str) -> List[Triple]:
        """Simple heuristic extraction of triples from text."""
        triples = []
        for i, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("---"):
                continue
            # Pattern: "user prefers X", "user likes Y", "X uses Y"
            m = re.search(r"(user|agent)\s+(prefers|likes|uses|avoids|dislikes)\s+(.+)", line, re.I)
            if m:
                subj, pred, obj = m.group(1), m.group(2), m.group(3).strip()
                triples.append(
                    Triple(
                        subject=subj.lower(),
                        predicate=pred.lower(),
                        obj=obj[:100],
                        confidence=0.6,
                        source=source,
                        line=i,
                    )
                )
            # Pattern: "X is Y"
            m = re.search(r"^(.+?)\s+is\s+(.+?)(?:\.|$)", line)
            if m:
                subj, obj = m.group(1).strip(), m.group(2).strip()
                triples.append(
                    Triple(
                        subject=subj[:50],
                        predicate="is",
                        obj=obj[:100],
                        confidence=0.5,
                        source=source,
                        line=i,
                    )
                )
        return triples

    def _extract_triples_llm(self, content: str, source: str) -> List[Triple]:
        """Extract triples using LLM (multi-provider)."""
        try:
            from .llm import get_provider

            provider = get_provider(provider_name=self.llm_provider)
            if not provider:
                return []
            text = provider.complete(
                [
                    {
                        "role": "system",
                        "content": "Extract factual statements as (subject, predicate, object) triples. One per line, format: SUBJECT | PREDICATE | OBJECT",
                    },
                    {"role": "user", "content": content[:3000]},
                ],
                max_tokens=500,
            )
            triples = []
            for i, line in enumerate(text.splitlines(), 1):
                if "|" in line:
                    parts = [p.strip() for p in line.split("|", 2)]
                    if len(parts) >= 3:
                        triples.append(
                            Triple(
                                subject=parts[0][:50],
                                predicate=parts[1][:30],
                                obj=parts[2][:100],
                                confidence=0.8,
                                source=source,
                                line=i,
                            )
                        )
            return triples
        except Exception:
            return []

    def extract_triples(self, content: str, source: str, use_llm: bool = False) -> List[Triple]:
        """Extract triples from content."""
        if use_llm and self.llm_provider:
            t = self._extract_triples_llm(content, source)
            if t:
                return t
        return self._extract_triples_simple(content, source)

    def _are_inverse(self, pred1: str, pred2: str) -> bool:
        """Check if predicates are inverses."""
        for a, b in INVERSE_PREDICATES:
            if (pred1 == a and pred2 == b) or (pred1 == b and pred2 == a):
                return True
        return False

    def _same_subject_object(self, t1: Triple, t2: Triple) -> bool:
        """Check if triples refer to same subject and object."""
        s1, o1 = t1.subject.lower(), t1.obj.lower()
        s2, o2 = t2.subject.lower(), t2.obj.lower()
        return (s1 == s2 and o1 == o2) or (s1 == o2 and o1 == s2)

    def detect_contradictions(self, triples: List[Triple]) -> List[Contradiction]:
        """Detect contradictions among triples."""
        contradictions = []
        for i, t1 in enumerate(triples):
            for t2 in triples[i + 1 :]:
                if self._same_subject_object(t1, t2) and self._are_inverse(
                    t1.predicate, t2.predicate
                ):
                    contradictions.append(
                        Contradiction(
                            triple1=t1,
                            triple2=t2,
                            reason=f"{t1.predicate} vs {t2.predicate}",
                        )
                    )
        return contradictions

    def check(self, use_llm: bool = False) -> ConsistencyResult:
        """Check consistency of semantic memories."""
        triples = []
        files_checked = 0

        if not self.current_dir.exists():
            return ConsistencyResult(valid=True, files_checked=0)

        semantic_dir = self.current_dir / "semantic"
        if not semantic_dir.exists():
            return ConsistencyResult(valid=True, files_checked=0)

        for f in semantic_dir.rglob("*.md"):
            if not f.is_file():
                continue
            try:
                rel = str(f.relative_to(self.current_dir))
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            files_checked += 1
            triples.extend(self.extract_triples(content, rel, use_llm))

        contradictions = self.detect_contradictions(triples)
        return ConsistencyResult(
            valid=len(contradictions) == 0,
            contradictions=contradictions,
            triples=triples,
            files_checked=files_checked,
        )

    def repair(self, strategy: str = "confidence") -> ConsistencyResult:
        """Attempt to auto-fix contradictions using strategy."""
        result = self.check(use_llm=(strategy == "llm"))
        if result.valid:
            return result
        # For now, repair just reports - actual fix would modify files
        return result
