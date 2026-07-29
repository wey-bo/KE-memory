# Frozen Official Architecture Audit

This directory records repository evidence only; none of Mem0, Graphiti, Hindsight, or MemPalace was installed or run.

The audit freezes Mem0 at `d653b63fac6c8ad0ad84aead0912b366e705d269`, Graphiti at `3bb2d0bba56f8e22311574c045452c420a012f49`, Hindsight at `ed120a256d51d731085ec8aca724573a7f2f1e1c`, and MemPalace at `8ab251c452c43f2b07a76a28f2433e258307f571`. `source-manifest.json` preserves immutable URLs, retrieval time, source excerpts, SHA-256 hashes, and local raw-byte source snapshots. The validator requires each source and claim excerpt to be an exact UTF-8 substring of its referenced snapshot. The immutable commit references remain the binding source identity.

`capability-matrix.json` contains only explicit official capabilities and one explicit non-shipped MemPalace capability. `gap-hypothesis-ledger.json` records testable architectural risks, not assertions that documentation absence proves a gap. Its controlled ablation entry is class-level evidence only and must never be presented as an unrun named system result.

`official-results-ledger.json` has no direct numeric comparison. A result can become `direct_numeric_comparison` only after benchmark version and split, base and answer models, context/retrieval budget, metric definition, and protocol are compatible with this experiment.
