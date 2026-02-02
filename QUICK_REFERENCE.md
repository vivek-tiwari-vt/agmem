# Quick Reference Guide: Using Fixed Components

## 1. Protocol Builder - Ensuring Schema Compliance

### Problem You're Solving
Client sends incompatible JSON to coordinator, getting 422 errors.

### Quick Start
```python
from memvcs.core.protocol_builder import ClientSummaryBuilder
from memvcs.core.federated import produce_local_summary
from pathlib import Path

# Get raw summary from your agent
raw_summary = produce_local_summary(
    repo_root=Path("."),
    memory_types=["semantic", "episodic"]
)

# Build protocol-compliant summary
compliant = ClientSummaryBuilder.build(
    repo_root=Path("."),
    raw_summary=raw_summary,
    strict_mode=False  # Warn instead of raising on validation errors
)

# Now safe to send to coordinator
import json
import urllib.request

req = urllib.request.Request(
    "http://coordinator:8000/push",
    data=json.dumps(compliant).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)
```

### Key Features
- **Automatic key mapping:** `topics` → `topic_counts`, `fact_count` → `fact_hashes`
- **Auto-generated agent_id:** Deterministic (same repo = same ID)
- **Auto-added timestamp:** ISO-8601 format
- **Schema validation:** Fails fast if output doesn't match server expectations

---

## 2. Privacy Validator - Preventing Metadata Noise

### Problem You're Solving
Accidentally applying differential privacy noise to metadata fields (clusters_found, confidence_score), which wastes entropy without providing privacy benefits.

### Quick Start - Using Validator
```python
from memvcs.core.privacy_validator import PrivacyFieldValidator

validator = PrivacyFieldValidator()

# This succeeds - noise on facts is good
validator.validate_noised_field("fact_count", 42, is_noised=True)

# This raises RuntimeError - noise on metadata is bad
try:
    validator.validate_noised_field("confidence_score", 0.95, is_noised=True)
except RuntimeError as e:
    print(f"Privacy violation: {e}")

# Get audit report
report = validator.get_report()
print(f"Noised fields: {report.noised_fields}")
print(f"Exempt fields: {report.exempt_fields}")
```

### Quick Start - Using Context Manager
```python
from memvcs.core.privacy_validator import PrivacyGuard

with PrivacyGuard(strict=True) as pg:
    # Mark fact fields as noised
    pg.mark_noised("fact_count", actual_count)
    pg.mark_noised("memory_count", memory_count)
    
    # Mark metadata as exempt
    pg.mark_exempt("clusters_found", cluster_count)
    pg.mark_exempt("created_at", timestamp)
```

### Quick Start - Using Decorator
```python
from memvcs.core.privacy_validator import privacy_exempt

@privacy_exempt
def get_metadata() -> Dict[str, Any]:
    # This function's results should NOT receive DP noise
    return {
        "clusters_found": 42,
        "created_at": "2024-01-01T00:00:00Z"
    }
```

---

## 3. Compression Metrics - Tracking Delta Encoding

### Problem You're Solving
Need visibility into whether delta encoding is actually helping. Which object types compress best? What savings are we getting?

### Quick Start
```python
from memvcs.core.compression_metrics import (
    DeltaCompressionMetrics,
    ObjectCompressionStats
)

# Initialize metrics collection
metrics = DeltaCompressionMetrics()

# During your packing operation, record each object:
for obj_id, original_content, compressed_content in your_objects:
    stats = ObjectCompressionStats(
        object_id=obj_id,
        object_type="semantic",  # or "episodic", "procedural"
        original_size=len(original_content),
        compressed_size=len(compressed_content),
        compression_ratio=len(compressed_content) / len(original_content),
        delta_used=True,  # Did we use delta encoding for this one?
        compression_benefit=len(original_content) - len(compressed_content)
    )
    metrics.record_object(stats)

# Generate report
report = metrics.get_report()
print(f"Total saved: {report['total_bytes_saved']:,} bytes")
print(f"Overall ratio: {report['overall_compression_ratio']:.1%}")

# Print heatmap
print(metrics.get_heatmap())

# Get recommendations
for rec in report['recommendations']:
    print(f"- {rec}")
```

### Output Example
```
Delta Compression Report
=======================================================================
Total Objects: 100
Total Original: 200,000 bytes
Total Compressed: 150,000 bytes
Overall Ratio: 75.0%
Bytes Saved: 50,000 (25.0%)

Delta Compression Heatmap
==================================================
semantic     ██████████████░░░░░░░░░░░░  35.0% saved (12/40 using delta)
episodic     ███████████████░░░░░░░░░░░  25.0% saved (5/35 using delta)
procedural   █████████████████████░░░░░  45.0% saved (20/25 using delta)
```

---

## 4. Fast Similarity Matcher - Solving Performance Bottleneck

### Problem You're Solving
Finding similar objects for delta encoding takes forever (40 billion Levenshtein distance operations for 100 objects). Need to pre-filter obviously-different objects.

### Quick Start
```python
from memvcs.core.fast_similarity import FastSimilarityMatcher

# Create matcher with tuned thresholds
matcher = FastSimilarityMatcher(
    length_ratio_threshold=0.5,   # Skip if sizes differ >50%
    simhash_threshold=15,          # Skip if SimHash Hamming dist >15
    min_similarity=0.8,            # Only return pairs with >80% similarity
    use_parallel=True,             # Use multiprocessing for speed
    max_workers=4                  # Use up to 4 CPU cores
)

# Find similar object pairs
objects = {
    "obj1": b"content1...",
    "obj2": b"content2...",
    "obj3": b"content3...",
    # ... more objects
}

similar_pairs = matcher.find_similar_pairs(objects)

# Results: list of (id1, id2, similarity_score) tuples
for obj1_id, obj2_id, similarity in similar_pairs:
    print(f"{obj1_id} ~ {obj2_id}: {similarity:.2%} similar")

# See filtering effectiveness
stats = matcher.get_statistics()
matcher.log_statistics()
```

### Output Example
```
Similarity Matching Statistics
==================================================
Total pairs evaluated: 4950
Filtered (Tier 1 - Length): 1980 (40.0%)
Filtered (Tier 2 - SimHash): 2450 (49.5%)
Evaluated (Tier 3 - Levenshtein): 520 (10.5%)
Similar pairs found: 42
==================================================
```

### Tuning the Thresholds

**For more aggressive filtering (faster, fewer matches):**
```python
matcher = FastSimilarityMatcher(
    length_ratio_threshold=0.3,   # Stricter length filter
    simhash_threshold=10,          # Stricter similarity filter
    min_similarity=0.9             # Require very similar
)
```

**For more thorough search (slower, more matches):**
```python
matcher = FastSimilarityMatcher(
    length_ratio_threshold=0.7,    # Looser length filter
    simhash_threshold=20,          # Looser similarity filter
    min_similarity=0.7             # Accept moderately similar
)
```

---

## 5. Running the Test Suite

### Run All Tests
```bash
# All critical tests (Tier 1, 2, 3 + performance)
pytest tests/tier1_test_cryptography.py \
        tests/tier2_test_workflows.py \
        tests/tier3_test_protocol.py \
        tests/test_performance_benchmarks.py -v

# Just Tier 1 (fastest, highest priority)
pytest tests/tier1_test_cryptography.py -v

# With coverage report
pytest tests/tier1_test_cryptography.py \
        tests/tier2_test_workflows.py \
        --cov=memvcs --cov-report=html

# Performance benchmarks only
pytest tests/test_performance_benchmarks.py -v -s
```

### Check Performance Regression
```bash
# These will fail if performance regresses >20%
pytest tests/test_performance_benchmarks.py::TestPerformanceRegression -v
```

---

## 6. Integration Examples

### Complete Push Workflow
```python
from pathlib import Path
from memvcs.core.federated import produce_local_summary
from memvcs.core.protocol_builder import ClientSummaryBuilder

repo_root = Path(".")

# Step 1: Produce local summary from memory
summary = produce_local_summary(
    repo_root=repo_root,
    memory_types=["semantic", "episodic"],
    use_dp=True,
    dp_epsilon=0.1
)

# Step 2: Ensure protocol compliance
compliant = ClientSummaryBuilder.build(repo_root, summary)

# Step 3: Send to coordinator
import urllib.request, json

req = urllib.request.Request(
    "http://localhost:8000/push",
    data=json.dumps(compliant).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urllib.request.urlopen(req, timeout=30) as resp:
    print(f"Server response: {resp.status}")
```

### Complete GC with Delta Encoding and Metrics
```python
from pathlib import Path
from memvcs.core.objects import ObjectStore
from memvcs.core.pack import run_repack
from memvcs.core.compression_metrics import DeltaCompressionMetrics

repo_root = Path(".")
objects_dir = repo_root / ".mem" / "objects"

# This now uses delta encoding automatically
freed_count, freed_bytes = run_repack(
    repo_root=repo_root,
    objects_dir=objects_dir,
    dry_run=False
)

print(f"Packed {freed_count} objects, freed {freed_bytes:,} bytes")

# To get compression details, integrate metrics tracking
# (See Compression Metrics section above)
```

---

## 7. Troubleshooting

### "SchemaValidationError: Missing required field"
**Cause:** Raw summary missing required fields
**Fix:** Ensure your summary has all required keys:
```python
# These keys are required:
required = {"memory_types", "topics", "topic_hashes", "fact_count"}
assert required <= set(raw_summary.keys()), "Missing keys!"
```

### "RuntimeError: Noise applied to exempt metadata field"
**Cause:** Trying to apply DP noise to a metadata field
**Fix:** Check which field is exempt and remove noise from it:
```python
# Don't noise these:
exempt = {"clusters_found", "insights_generated", "confidence_score"}

# Only noise fact fields:
fact_fields = {"fact_count", "memory_count", "facts"}
```

### "Performance regressed >20% on Levenshtein"
**Cause:** Algorithm change or inefficient implementation
**Fix:** Check if FastSimilarityMatcher pre-filters are working:
```python
stats = matcher.get_statistics()
if stats["evaluated_tier3_levenshtein"]["count"] / stats["total_pairs_evaluated"] > 0.3:
    print("WARNING: Too many pairs reaching Levenshtein!")
    # Increase filtering thresholds
```

---

## 8. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   AGMEM Memory Agent                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Memory Collection                                          │
│  └─ episodic/, semantic/, procedural/ memory files         │
│                                                              │
│  produce_local_summary()                                    │
│  └─ Extracts topics, hashes, counts                        │
│                                                              │
│  ClientSummaryBuilder ─────────────────────────┐            │
│  └─ Schema validation                          │            │
│  └─ Key mapping & timestamp                    │            │
│  └─ Agent ID generation                        │ Protocol   │
│                                                 │ Compliance │
│  PrivacyValidator ──────────────────────────────┤            │
│  └─ DP noise (only on facts, not metadata)     │            │
│  └─ Audit report generation                    │            │
│                                                 │            │
└──────────────────────────────────────────────────────────────┘
                            │
                            │ {"summary": {...}} ← Protocol compliant
                            │
                            ▼
                   ┌────────────────┐
                   │   Coordinator  │
                   │    Server      │
                   │   (FastAPI)    │
                   └────────────────┘

┌─────────────────────────────────────────────────────────────┐
│               GC & Packing Pipeline                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  find_similar_objects() ──┐                                 │
│                            │ FastSimilarityMatcher           │
│  Tier 1: Length filter ────┤ └─ Eliminates 40-50%          │
│  Tier 2: SimHash filter ───┼─ └─ Eliminates 30-40%         │
│  Tier 3: Levenshtein  ─────┘ └─ Only 5-10% remain          │
│                                                              │
│  write_pack_with_delta()                                    │
│  └─ Delta encoding                                          │
│  └─ Compression metrics tracking                            │
│  └─ Performance optimization recommendations                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Next Steps

1. **Run the test suite** to validate all fixes:
   ```bash
   pytest tests/tier*.py tests/test_performance_benchmarks.py -v
   ```

2. **Review and integrate privacy validator** into Gardener and Distiller:
   - Remove metadata noise from Gardener (clusters_found, insights_generated, episodes_archived)
   - Remove confidence_score noise from Distiller

3. **Monitor compression metrics** in gc output to understand delta encoding effectiveness

4. **Tune FastSimilarityMatcher thresholds** based on your object characteristics

5. **Set up CI coverage gates** to prevent regressions:
   - Tier 1+2: 85% coverage minimum
   - Overall: 70% coverage minimum
   - Performance: Fail if regression >20%

---

For detailed API documentation, see the docstrings in each module.
For implementation details, see `/Volumes/DATA/amvcs/IMPLEMENTATION_REPORT.md`.
