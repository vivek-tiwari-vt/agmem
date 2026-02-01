# agmem Stress Test Report

Generated: 2026-01-31T15:06:56.958439

**Summary:** 26/26 passed, 0 failed

## Results

- ✅ **init (basic)** (0.002s)
- ✅ **init (already exists fails)** (0.000s)
- ✅ **empty file** (0.001s)
- ✅ **unicode content** (0.001s)
- ✅ **binary content** (0.001s)
- ✅ **special chars filename** (0.001s)
- ✅ **deep nesting** (0.001s)
- ✅ **newlines only** (0.001s)
- ✅ **many files (50)** (0.034s)
- ✅ **content deduplication** (0.002s)
- ✅ **1MB file** (0.004s)
- ✅ **10MB file** (0.037s)
- ✅ **50MB file** (0.203s)
- ✅ **very long line (100KB)** (0.002s)
- ✅ **commit and retrieve** (0.100s)
- ✅ **log walk** (0.000s)
- ✅ **tag operations** (0.000s)
- ✅ **merge success (no conflict)** (0.007s)
- ✅ **merge conflict detection** (0.008s)
- ✅ **checkout restore** (0.011s)
- ✅ **status categories** (0.002s)
- ✅ **all CLI commands** (0.530s)
- ✅ **agmem tree** (0.062s)
- ✅ **agmem diff** (0.071s)
- ✅ **agmem show** (0.064s)
- ✅ **agmem reset --hard** (0.069s)

## Edge Cases Covered

- Empty files
- Large files (1MB, 10MB)
- Unicode content
- Binary content
- Special characters in filenames
- Deep directory nesting
- Many files (50+)
- Content deduplication
- Merge conflicts
- Checkout/restore
