# Sequential validation (post-implementation)

After completing the feature plan, validate main user flows and document gaps.

## Flows to validate

1. **init → add → commit → branch → merge** — Core Git-like workflow; unchanged.
2. **push/pull** — file:// unchanged; s3:///gs:// now use storage adapter + distributed lock (acquire before, release in finally).
3. **garden/distill with --private** — Budget checked and spent; add_noise applied to counts and frontmatter (Gardener: clusters_found, insights_generated, episodes_archived, source_episodes; Distiller: fact_count, confidence_score, clusters_processed, facts_extracted, episodes_archived).
4. **gc/repack** — run_gc deletes unreachable loose objects; --repack runs run_repack to pack reachable loose into pack file + index, then deletes those loose; ObjectStore.retrieve reads from pack when loose missing.
5. **prove/verify** — prove_keyword_containment (Merkle set membership) and prove_memory_freshness (signed timestamp) produce proofs; verify_proof checks them.
6. **federated push/pull** — produce_local_summary builds topic counts and topic_hashes; optional DP noising; push_updates/pull_merged HTTP to coordinator (no in-package server).
7. **IPFS** — push_to_ipfs bundles objects and POSTs to gateway /api/v0/add; pull_from_ipfs GETs by CID and unbundles into loose objects.
8. **when/timeline --from/--to** — Temporal range filter via TemporalIndex.range_query; only commits in range included.
9. **Daemon health** — health_check_interval from config or AGMEM_DAEMON_HEALTH_INTERVAL; on verify failure only stderr + suggest agmem fsck.

## Known gaps / edge cases

- **ZK freshness** — Requires AGMEM_SIGNING_PRIVATE_KEY (or AGMEM_SIGNING_PRIVATE_KEY_FILE) in env to produce proof; verify works with proof that embeds public_key_pem_b64.
- **IPFS gateway** — Many public gateways are read-only; POST /api/v0/add may fail. Use a writable gateway or local IPFS daemon (ipfshttpclient) for push.
- **Cloud remote** — Clone still uses parse_remote_url (file only); push/fetch support s3:// and gs:// with lock. Clone from s3/gs not implemented.
- **Pack** — Single pack file per run_repack; ObjectStore reads from first .idx found in objects/pack (no multi-pack merge yet).
