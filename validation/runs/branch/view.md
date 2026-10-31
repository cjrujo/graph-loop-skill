Graph `branch` · version 1 · revision 14

| Node | Owner | State | Dependencies | Evidence (kind/verdict) | Risk / next step |
|---|---|---|---|---|---|
| select | single-agent-fixture | succeeded | — | [select-check.json](select-check.json) (execution/pass, v1) | see node loop and dependency state |
| small | single-agent-fixture | succeeded | select | [small-check.json](small-check.json) (execution/pass, v1) | see node loop and dependency state |
| large | single-agent-fixture | skipped | select | none | see node loop and dependency state |
| join | single-agent-fixture | succeeded | small, large | [join-check.json](join-check.json) (execution/pass, v1) | see node loop and dependency state |

```mermaid
flowchart TD
  n0["select: succeeded"]
  n1["small: succeeded"]
  n0 --> n1
  n2["large: skipped"]
  n0 --> n2
  n3["join: succeeded"]
  n1 --> n3
  n2 --> n3
```

Snapshot validation does not prove output correctness, permissions, transition history or deadline enforcement.
