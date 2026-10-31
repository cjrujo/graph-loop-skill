# Complete chat-only recovery snapshot

No durable filesystem/export/wakeup is available. The user must copy/save **all** sections of this snapshot; the AI cannot guarantee cross-session recovery. Report the graph/version/revision and loss window before work. Refresh at each finite safe chunk and on an observed pause. If generation is terminated before this copy is emitted, later work may be lost.

Use a full v2 state from state-template.json, not a truncated diff. Replace placeholders from actual observations. For small tasks, inline all required files/evidence below with exact contents and SHA-256 when hash tooling is available. If hashing is unavailable, label it `not computed` and require independent revalidation; do not fabricate a hash or claim helper compatibility. Include necessary user decision excerpts with provenance, omit secrets and unrelated private text. Missing external items must be explicit blockers, not absolute paths presented as portable files.

```text
SNAPSHOT_BEGIN
Graph ID / lineage / graph version / revision:
Lifecycle: paused | interrupted | cancelled | active (actual observed status)
Authority: this explicitly versioned snapshot; latest known revision:
Retrieval: user copies this entire message and included files; no background persistence
Scope / acceptance / current authorization source references:
FULL_V2_STATE_JSON_BEGIN
[paste the complete state, every node including safe cursor, phase, next safe action,
inputs/outputs/evidence versions, branch, operations, cumulative attempts/usage/limits]
FULL_V2_STATE_JSON_END
FILE_BEGIN [relative ref, role, version, SHA-256 or explicitly not computed]
[entire necessary input/output/context/verification evidence; repeat for each file]
FILE_END
MISSING_EXTERNAL_ITEMS [ref, affected node, reason and needed current access]
PROGRESS [finished/unfinished, last committed safe step, next safe action, risks]
MANIFEST [exact list of included file refs and hashes or unverified status]
AUTHORITY_FRESHNESS [last known source; what must be rechecked next session]
RESUME_PROMPT [include the full English text from resume-prompt.en.md]
SNAPSHOT_END
```

This is a fill-in format, not an executed example. Do not claim it is portable until it contains the actual state/files or explicitly disclosed missing requirements. Chat copy/retain behavior and model compliance have not been tested by the local Python fixtures.
