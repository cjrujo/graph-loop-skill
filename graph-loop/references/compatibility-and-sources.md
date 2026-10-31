# Compatibility, installation and primary sources

Historical rc2 source review dated 2026-10-31; not re-browsed for this recovery-only revision. Recheck official docs before installation. Documentation establishes a supported mechanism, not that this package was installed or behaviorally evaluated in that host. Product version, environment, admin policy and enabled tools can change support. No seven-host compatibility claim is made.

## Support matrix

| Host | Native mechanism documented | Candidate route after local detection | Evidence / actual package validation |
|---|---|---|---|
| Codex | Agent Skills; local repository and user discovery | Repository `.agents/skills/graph-loop/`; user `~/.agents/skills/graph-loop/` only if that scope is requested | [Official OpenAI documentation](https://learn.chatgpt.com/docs/build-skills), redirected from `developers.openai.com/codex/skills/`. Package structure checked locally; discovery/activation in a fresh Codex host not tested |
| Claude Code | Agent Skills with host extensions | Repository `.claude/skills/graph-loop/`; user `~/.claude/skills/graph-loop/` if requested | [Official skills docs](https://code.claude.com/docs/en/skills). Package not installed/tested; cloud/account routes differ from local CLI |
| Pi | Agent Skills, on-demand loading | Verified `.agents/skills/graph-loop/` project or `~/.agents/skills/graph-loop/` user route; use current Pi configuration for other locations | [Maintainer documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md), redirected from badlogic/pi-mono. Package not installed/tested |
| OpenCode | Native `skill` tool loads SKILL.md | Repository `.opencode/skills/graph-loop/`; user `~/.config/opencode/skills/graph-loop/` if requested; `.agents/skills` compatibility route also documented | [Official skills docs](https://opencode.ai/docs/skills/). Package not installed/tested |
| WorkBuddy (Tencent) | Official skill market/import workflow and SKILL.md bundle documented | Detect exact edition and its available local/import UI. Open-platform market schema requires additional display/author/version/language fields; adapt a separate copy only when that route is requested | [Official open-platform schema](https://open.workbuddy.cn/docs/skill). No universal local path or unmodified market acceptance claimed; import/runtime not tested |
| Muse | Exact vendor/product/version not supplied | Identify from current host metadata or user-supplied official URL. Until identified use manual loading/prompt fallback if files/text can be read | Identity and native skill mechanism unverified; no path inferred from the name |
| Dot | Exact vendor/product/version not supplied | Same identity-first detection; manual loading/prompt fallback where possible | Identity and native skill mechanism unverified; no path inferred from the name |

The current authoring environment exposes a Codex skill catalog and Python 3. That is not an installation test of this new skill. Claude Code, Pi and OpenCode executables were absent at inspection; WorkBuddy, Muse and Dot sessions were not available. The local fixtures exercise file-copy mechanics and state handling, not these products.

## Installation behavior

Keep the entire `graph-loop/` directory intact. Detect the host and version, inspect its current official skill documentation and local discovery settings, then choose the smallest authorized scope, preferably project-local. Existing same-name files require a diff and explicit overwrite instruction; never replace unrelated configuration. Do not edit permission policy, enable delegation, install dependencies, publish a market listing, or write to GitHub just to load this skill.

Before copying, inspect the supplied bundle and any scripts. If receiving an archive, reject absolute/parent-traversal paths and unsafe symlinks; extract into an isolated staging directory. Confirm the root that directly contains `SKILL.md`, not a nested wrapper folder. Copy that folder to the verified skill directory. Read back the name, description and resource paths; check discovery in the host and invoke explicitly if available. Run a harmless task and inspect its graph/loop/evidence output. A copied file alone proves only copying, not discovery or activation.

If the host has no native skills, cannot write files, or cannot verify a path: keep a task-local copy or load the SKILL.md text and relevant references manually as instructions for the current task. State the limitations: no native auto-discovery, no automatic cross-session persistence or guaranteed script execution. Do not describe this as native installation. Text-only hosts can use a versioned chat table and bounded manual loops.

## Optional existing-tool mappings

| Available tool | Mapping | Boundary |
|---|---|---|
| Host plan/task tool | Node IDs, dependency references and status plus an evidence field/link; host store is authoritative | A task checklist may lack graph/version semantics; retain a minimal linked record only for missing fields and define which fields each owns |
| LangGraph | State → authoritative record; nodes → bounded work/check steps; edges/conditional edges → dependencies/branches; join → selected predecessor checks | [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) documents these primitives. Mapping is a design, no adapter or runtime test shipped |
| LangGraph persistence | Checkpoints keyed to a thread/run for recovery | [Persistence docs](https://docs.langchain.com/oss/python/langgraph/persistence) distinguish checkpointers/stores. RAM-only checkpoints do not survive restart; choose an already available durable store when needed |
| AutoGen AgentChat | Existing teams can use message/token/time/external termination as ceilings; coordinator validates returned artifacts | [Official termination docs](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html). A text stop marker alone is not acceptance evidence. No AutoGen installation/adapter test performed |

When mapping, use one state source or one clearly defined field owner; do not keep two independent statuses. Concurrency, framework installation and external actions remain subject to the user's/host's existing permissions. The skill does not require any of these tools.

## Format source and scope

The [Agent Skills specification](https://agentskills.io/specification) defines a directory with `SKILL.md`, required YAML `name` and `description`, and optional supporting directories. `graph-loop` matches its containing directory, uses portable name characters, and has a short entrypoint linking references/assets/scripts. Version is a string in optional `metadata`. No `allowed-tools`, fork directive, hook, or tool permission expansion is declared.

Graph states, limits and JSON schema in this package are workflow conventions; they are not part of the Agent Skills specification. The bundled inspector and recovery store helper are optional, standard-library Python 3.10+ code. The helper is a local persistence/export utility, not a host integration or scheduler. It does not add runtime dependencies to the instruction-only workflow.

All links above are primary specification, vendor, framework or maintainer sources opened on the checked date. Local skill-creator guidance was also read for progressive disclosure and validation. Recheck live docs before a future installation; a standard bundle format does not unify every host's install API or marketplace schema.
