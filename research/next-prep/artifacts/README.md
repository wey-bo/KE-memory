# Next-prep artifact snapshot

This directory contains copied research artifacts from the active next-prep workspace. These files are kept for audit, handoff, and branch-local follow-up work; they are not runtime package outputs.

Large generated run directories were intentionally excluded, especially:

```text
artifacts/ontology-memory-experiment/runs/
```

Use the reports, frozen gold, manifests, and compact ledgers in this snapshot for context. Recreate heavy run outputs from their frozen inputs when needed.

Do not add future automatic evaluation framework code here. Promote reusable automatic evaluation logic to the repository's future `eval/` area only after the runtime end-to-end flow and fixture contracts are stable.
