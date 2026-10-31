# Graph & Loop — 1.0.0-rc3 recovery candidate

An English Agent Skill for task-sized dependency graphs, bounded work/verify/repair loops, node-internal durable checkpoints, explicit pause/resume and portable recovery snapshots. This revision reuses frozen rc2; it is a candidate for independent review, with no publication approval implied.

Start with [SKILL.md](graph-loop/SKILL.md), [English install prompt](install-prompt.en.md), [English resume prompt](resume-prompt.en.md), [recovery contract](graph-loop/references/pause-and-recovery.md), and the [Chinese user demo](user-demo.zh-CN.md). [Chinese review](review.zh-CN.md) describes scope and changes; [verification report](validation/verification-report.zh-CN.md) separates executed fixtures, simulation, document checks and untested behavior.

The standard `graph-loop.zip` includes all used references/assets/scripts, including the resume prompt and chat fallback. The full `graph-loop-review-bundle.zip` includes source, fixtures, historical rc2 evidence (explicitly historical), logs and per-file hashes. [release-manifest.json](release-manifest.json) records final source/archive bytes, excluding itself.

## Stop now; continue next session

Before work the AI must give you the authority's actual retrieval route and latest versioned export's download/copy location. On pause, keep **the latest recovery ZIP** it actually gives you, or the **entire versioned chat snapshot**. Next session attach that package and paste [resume-prompt.en.md](resume-prompt.en.md), with current scope/authority details filled in. A package alone is not a request to resume. Do not give a new AI only a local absolute path it cannot read.

For a concrete, self-contained **fixed simulated workload**, use [examples/portable-demo-v1-r5.zip](examples/portable-demo-v1-r5.zip). It contains raw state, progress, six referenced input/output/context/evidence files, provenance, SHA-256 manifest and English resume prompt. The stopped node has committed step 1; selector/small branch already succeeded, large branch is excluded. There are no missing external dependencies for this local fixture. Its authority statements authorize no real external actions.

## Local helper (optional)

The skill itself needs no runtime. `inspect_state.py` is read-only. `recovery_store.py` uses Python 3.10+ standard library for atomic local checkpoint envelopes, previous-version retention, checks and portable import/export. It does not execute nodes, enforce user permissions, stop tools, schedule checkpoints, wake an AI or guarantee exactly-once behavior. Full commands and manual alternatives are in [pause and recovery](graph-loop/references/pause-and-recovery.md).

```bash
python3 graph-loop/scripts/inspect_state.py graph-loop/assets/state-template.json --check
PYTHONDONTWRITEBYTECODE=1 python3 validation/run_validation.py
PYTHONDONTWRITEBYTECODE=1 python3 validation/run_recovery_validation.py
python3 validation/package_and_check.py
PYTHONDONTWRITEBYTECODE=1 python3 validation/check_isolated_skill_package.py
python3 validation/package_and_check.py
```

Tests rewrite their run evidence; repack afterward to refresh manifests. Packaging also uses only the standard library; the separately executed official skill-creator validator uses the environment's existing PyYAML. No dependency/global installation is required or authorized.

## Evidence boundary

The current run passed 20 existing deterministic cases and 18 additional recovery checks. Real local subprocess SIGKILL, explicit stdin pause, isolated-process import/resume and byte-level archive checks were executed. Workloads and provider effects are fixed simulations; fallback coverage is document inspection. These results do not establish AI instruction adherence, seven-host compatibility, arbitrary crash-offset coverage, real-provider behavior or power-loss durability. Recovery may lose work since the last committed checkpoint; unknown effects block replay. Historical support links were retained from rc2 and were not re-browsed for this recovery-only revision.
