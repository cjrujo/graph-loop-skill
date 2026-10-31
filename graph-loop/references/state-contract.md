# State and execution contract

Read [pause and recovery](pause-and-recovery.md) for the v2 fields, lifecycle, durable storage and portable package contract. These are Graph & Loop conventions. Hosts may map them onto native fields without duplicating their state store. The optional JSON helper checks a subset of invariants; the coordinator remains responsible for transitions, real evidence, and authority.

## Record and views

Maintain `graph_id`, `graph_version` (positive integer; topology/contract/input changes), `revision` (monotonically increasing on every committed update), objective, acceptance, constraints, assumptions, authority sources, context references, limits, and nodes. Persist the complete snapshot atomically or use the host's transactional API. One coordinator writes it; workers propose updates against a version/revision. Reject or reconcile stale writes. Never silently last-write-wins a concurrent result.

The optional JSON form has:

| Field | Meaning |
|---|---|
| `schema_version` | `2` for the recovery contract; inspector also accepts legacy `1` for historical fixtures |
| `objective`, `acceptance`, `constraints`, `assumptions` | Outcome and explicitly labeled scope |
| `authorization` | Statements linking existing permissions/gates to their sources; does not grant authority |
| `context_sources` | `{ref, trust}` source pointers; trust describes provenance, not instruction priority |
| `limits` | `max_parallel`, `deadline_utc`, optional cost/token/work caps and observed usage |
| node `id`, `owner`, `task` | Stable ID, single accountable owner, bounded work |
| `inputs`, `outputs`, `depends_on` | References and predecessor IDs; edge direction is predecessor → node |
| `branch` | Optional `{node, equals}`; refers to a predecessor's recorded `selection` |
| `status`, `attempts`, `no_progress` | Current status, cumulative starts, consecutive attempts without measurable progress |
| `loop` | `entry`, `work`, `verify`, `repair`, `max_attempts`, `max_no_progress`; specify a measurable progress criterion in the text |
| `evidence` | Array of `{ref, kind, verdict, graph_version}`; kinds: `execution`, `inspection`, `simulation`, `not_run`; verdicts: `pass`, `fail`, `not_run` |
| `artifacts` | Array of `{ref, graph_version, validity}`; validity is `current` or `stale`; optional hash/version |
| `reason`, `resume_when` | Required for blocked; concrete cause and observable change needed |
| `allow_simulation` | Default false; true only if the declared task outcome is itself a simulation |

A snapshot need not repeat raw files or whole conversations. Keep evidence resolvable and protect sensitive content. Chat-only snapshots retain the same logical contract but lack durable recovery guarantees.

## Node states and edges

| State | Entry / allowed next states |
|---|---|
| `pending` | Not eligible yet → `ready`, `blocked`, `skipped`, `cancelled` |
| `ready` | Dependencies/inputs/authority/budget/entry checked → `running`, `blocked`, `cancelled` |
| `running` | Increment attempt, checkpoint → `verifying`, `failed`, `blocked`, `cancelled` |
| `verifying` | Compare acceptance and attach evidence → `succeeded`, `failed`, `blocked`, `cancelled` |
| `failed` | Check failed or finite limit reached → `ready` only for a changed, permitted repair with remaining budget; otherwise terminal |
| `blocked` | Missing external condition → `pending` for fresh entry validation after the recorded trigger changes; do not consume attempts by polling |
| `succeeded` | Terminal for this contract/version; output and passing evidence are current |
| `skipped` | Excluded by an evidenced branch selection; never represents missing required work |
| `paused` | Suspended by user, preserving `resume_status`, phase, committed cursor and counters; only explicit resume plus preflight can return to that status |
| `cancelled` | Explicitly cancelled or superseded; never counted as success |

Success requires the actual acceptance check to pass, not merely a nonempty artifact or a worker's claim. `not_run` evidence can never be passing evidence. Simulation can satisfy only an explicitly declared simulation node and must still be labeled in user views.

Keep the dependency graph acyclic. Repetition lives inside bounded node loops. For rework across nodes, create a new graph version with invalidation; do not hide an unbounded graph cycle.

**Fork:** After a predecessor succeeds, independent nodes may become eligible. Execute concurrently only within authorized worker/tool/resource limits and disjoint write boundaries. A single-agent host can run the same nodes serially.

**Branch:** Record the selector's observed decision and evidence before marking excluded nodes `skipped`. The selector must be a dependency. An unresolved decision leaves nodes pending. Changing a decision requires replan and invalidation.

**Join:** Default is ALL selected dependencies succeeded with current evidence and artifacts. A skipped predecessor satisfies a join only when its branch predicate demonstrably excludes it. A failed, blocked, cancelled, unknown, or stale predecessor never satisfies a required edge. ANY/quorum behavior requires an explicit alternative contract and a documented decision; it is outside the optional helper's JSON subset.

**Failure propagation:** Preserve the cause at its origin. Mark only affected descendants blocked with the upstream ID and trigger; continue independent eligible work. Do not relabel upstream failure as downstream success. If an alternative is within the task's scope, replan visibly; otherwise report incomplete work.

## Budgets, retry, interruption

Define total starts (`max_attempts`, including the first), consecutive no-progress limit (`max_no_progress`), time/work allowance, optional observed cost/token caps, and parallel cap before starting. Choose smaller limits for external effects. The first failure can count as no progress if its declared metric has not improved. A useful failure that identifies a new actionable cause may count as progress only with that evidence. Reset the no-progress counter only on measured progress, not a rephrased plan.

Check all ceilings before starting and between meaningful work steps; a long tool operation needs the host's timeout/cancellation mechanism. At a hard limit stop launching work, cancel safely if supported, checkpoint, and report unmet criteria. A retry consumes another attempt. Replanning or resuming never resets the task's consumed time/cost or unchanged work's attempts. Increase a limit only within existing authority; otherwise use the existing approval path for that action.

For an uncertain external write, store action identity/idempotency key and reconcile actual provider state before retrying. A timeout alone is not proof of failure. If reconciliation is impossible, block that action and report ambiguity; continue independent work.

On recovery, load the latest source, confirm its version/revision and authority references, check input/artifact hashes or versions, and reconcile in-flight operations. `running` after a crash is ambiguous, not automatically retryable. Resume through fresh entry checks, preserving counters and failure evidence. Never invent a timer or watcher: describe one only if the host actually scheduled it.

## Replan and completion

On changed topology, input, acceptance, or material assumption: checkpoint; increment graph version and revision; record the delta and reason. Mark changed nodes and all consumers' old artifacts stale; invalidate their prior success. Cancel/ignore late worker results from the old version. Retain history for audit. Reuse unaffected results only after explicit input/contract equivalence checks; carry their evidence into the new version with provenance.

Do not mutate a historical success's evidence to appear current without checking it. Remove stale data from active inputs, caches and prompt context. Resume affected nodes as pending with their consumed budgets retained. Old artifacts may remain archived with stale labels; never allow a current join to consume them.

Task completion requires every required selected node succeeded and the overall acceptance satisfied. An excluded branch may be skipped; optional work must have been declared optional, with its omission disclosed. Save a final view with outputs, evidence, unresolved risks and any handoff. A graph with stopped/blocked required work is an incomplete result even if all executable work has stopped.
