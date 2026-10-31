#!/usr/bin/env python3
"""Read-only validation/rendering of Graph & Loop v1/v2 JSON snapshots. No scheduler."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit

STATES = {"pending", "ready", "running", "verifying", "succeeded", "failed", "blocked", "skipped", "cancelled", "paused"}
ACTIVE = {"running", "verifying"}
ELIGIBLE = {"ready", "running", "verifying", "succeeded"}
ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class InvalidState(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise InvalidState(message)


def positive(value):
    return type(value) is int and value > 0


def strings(value, nonempty=False):
    return isinstance(value, list) and (bool(value) or not nonempty) and all(isinstance(x, str) and x.strip() for x in value)


def validate(s):
    need(isinstance(s, dict), "state must be an object")
    need(type(s.get("schema_version")) is int and s["schema_version"] in {1, 2}, "unsupported schema_version")
    need(isinstance(s.get("graph_id"), str) and ID.fullmatch(s["graph_id"]), "invalid graph_id")
    for k in ("graph_version", "revision"):
        need(positive(s.get(k)), f"{k} must be a positive integer")
    need(isinstance(s.get("objective"), str) and s["objective"].strip(), "objective required")
    for k in ("acceptance", "constraints", "assumptions", "authorization"):
        need(strings(s.get(k), k in {"acceptance", "authorization"}), f"invalid {k}")
    need(isinstance(s.get("context_sources"), list), "context_sources required")
    for source in s["context_sources"]:
        need(isinstance(source, dict) and all(isinstance(source.get(k), str) and source[k].strip() for k in ("ref", "trust")), "invalid source")
    limits = s.get("limits")
    need(isinstance(limits, dict) and positive(limits.get("max_parallel")), "finite max_parallel required")
    try:
        deadline = datetime.fromisoformat(limits["deadline_utc"].replace("Z", "+00:00"))
        need(deadline.tzinfo is not None, "deadline must include timezone")
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise InvalidState("valid deadline_utc required") from exc
    nodes = s.get("nodes")
    need(isinstance(nodes, list) and nodes, "nonempty nodes required")
    by_id = {}
    for n in nodes:
        need(isinstance(n, dict), "node must be object")
        node_id = n.get("id")
        need(isinstance(node_id, str) and ID.fullmatch(node_id), "invalid node id")
        need(node_id not in by_id, "duplicate node id")
        by_id[node_id] = n
        for k in ("owner", "task"):
            need(isinstance(n.get(k), str) and n[k].strip(), f"{node_id}: {k} required")
        for k in ("inputs", "outputs", "depends_on"):
            need(strings(n.get(k)), f"{node_id}: invalid {k}")
        need(len(n["depends_on"]) == len(set(n["depends_on"])), f"{node_id}: duplicate dependency")
        need(n.get("status") in STATES, f"{node_id}: invalid status")
        for k in ("attempts", "no_progress"):
            need(type(n.get(k)) is int and n[k] >= 0, f"{node_id}: invalid {k}")
        need(n["no_progress"] <= n["attempts"], f"{node_id}: impossible no_progress counter")
        loop = n.get("loop")
        need(isinstance(loop, dict), f"{node_id}: loop required")
        for k in ("entry", "work", "verify", "repair"):
            need(isinstance(loop.get(k), str) and loop[k].strip(), f"{node_id}: loop {k} required")
        for k in ("max_attempts", "max_no_progress"):
            need(positive(loop.get(k)), f"{node_id}: finite {k} required")
        need(n["attempts"] <= loop["max_attempts"], f"{node_id}: attempt budget exceeded")
        if n["status"] == "ready":
            need(n["attempts"] < loop["max_attempts"], f"{node_id}: no attempt remains")
        if n["status"] in {"ready", "running", "verifying"}:
            need(n["no_progress"] < loop["max_no_progress"], f"{node_id}: no-progress limit reached")
        if n["status"] in ACTIVE | {"succeeded"}:
            need(n["attempts"] > 0, f"{node_id}: work without attempt")
        if n["status"] in {"blocked", "failed", "cancelled"}:
            need(isinstance(n.get("reason"), str) and n["reason"].strip(), f"{node_id}: reason required")
        if n["status"] == "blocked":
            need(isinstance(n.get("resume_when"), str) and n["resume_when"].strip(), f"{node_id}: resume_when required")
        need(type(n.get("allow_simulation", False)) is bool, f"{node_id}: invalid allow_simulation")
        need(isinstance(n.get("artifacts"), list), f"{node_id}: artifacts required")
        for a in n["artifacts"]:
            need(isinstance(a, dict) and isinstance(a.get("ref"), str) and a["ref"].strip(), f"{node_id}: invalid artifact")
            need(positive(a.get("graph_version")) and a["graph_version"] <= s["graph_version"], f"{node_id}: invalid artifact version")
            need(a.get("validity") in {"current", "stale"}, f"{node_id}: invalid artifact validity")
            if a["validity"] == "current":
                need(a["graph_version"] == s["graph_version"], f"{node_id}: current artifact from old version")
        need(isinstance(n.get("evidence"), list), f"{node_id}: evidence required")
        for e in n["evidence"]:
            need(isinstance(e, dict) and isinstance(e.get("ref"), str) and e["ref"].strip(), f"{node_id}: invalid evidence reference")
            need(e.get("kind") in {"execution", "inspection", "simulation", "not_run"}, f"{node_id}: invalid evidence kind")
            need(e.get("verdict") in {"pass", "fail", "not_run"}, f"{node_id}: invalid verdict")
            need(positive(e.get("graph_version")) and e["graph_version"] <= s["graph_version"], f"{node_id}: invalid evidence version")
            need(e["kind"] != "not_run" or e["verdict"] == "not_run", f"{node_id}: not_run cannot pass/fail")
        if n["status"] == "succeeded":
            allowed = {"execution", "inspection"} | ({"simulation"} if n.get("allow_simulation", False) else set())
            need(any(e["graph_version"] == s["graph_version"] and e["verdict"] == "pass" and e["kind"] in allowed for e in n["evidence"]), f"{node_id}: no current passing evidence")
            need(all(a["validity"] == "current" for a in n["artifacts"]), f"{node_id}: stale artifact on success")
            need(set(n["outputs"]) <= {a["ref"] for a in n["artifacts"]}, f"{node_id}: output artifact missing")
    need(sum(n["status"] in ACTIVE for n in nodes) <= limits["max_parallel"], "parallel cap exceeded")
    for n in nodes:
        for dep in n["depends_on"]:
            need(dep in by_id and dep != n["id"], f"{n['id']}: invalid dependency")
        branch = n.get("branch")
        if branch is not None:
            need(isinstance(branch, dict) and branch.get("node") in n["depends_on"], f"{n['id']}: selector must be a dependency")
            need(isinstance(branch.get("equals"), str) and branch["equals"].strip(), f"{n['id']}: invalid branch value")
        if n["status"] in ELIGIBLE:
            if branch:
                selector = by_id[branch["node"]]
                need(selector["status"] == "succeeded" and selector.get("selection") == branch["equals"], f"{n['id']}: unselected branch executed")
            for dep in n["depends_on"]:
                need(by_id[dep]["status"] in {"succeeded", "skipped"}, f"{n['id']}: dependency not satisfied: {dep}")
        if n["status"] == "skipped":
            need(branch is not None, f"{n['id']}: skipped without branch")
            selector = by_id[branch["node"]]
            need(selector["status"] == "succeeded" and isinstance(selector.get("selection"), str) and selector["selection"] != branch["equals"], f"{n['id']}: branch exclusion unproven")
    visited, visiting = set(), set()

    def visit(node_id):
        need(node_id not in visiting, "dependency cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in by_id[node_id]["depends_on"]:
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in by_id:
        visit(node_id)
    if s["schema_version"] == 2:
        validate_recovery(s)
    return s


def validate_recovery(s):
    need(isinstance(s.get("lineage_id"), str) and s["lineage_id"].strip(), "lineage_id required")
    life = s.get("lifecycle", {})
    need(life.get("status") in {"active", "pause_requested", "paused", "interrupted", "cancelled", "completed"}, "invalid lifecycle")
    need(isinstance(life.get("reason"), str) and life["reason"], "lifecycle reason required")
    recovery = s.get("recovery", {})
    for k in ("authority_location", "retrieval", "export_policy"):
        need(isinstance(recovery.get(k), str) and recovery[k], "recovery " + k + " required")
    def finite(x):
        return type(x) in {int, float} and 0 <= x < float("inf")
    def usage(u):
        need(isinstance(u, dict) and all(finite(u.get(k)) for k in ("work_units", "elapsed_seconds")), "invalid cumulative usage")
        for k in ("tokens", "cost_usd"):
            need(u.get(k) is None or finite(u[k]), "invalid observed usage")
    def interval(i):
        need(isinstance(i, dict) and positive(i.get("max_work_units")) and finite(i.get("max_seconds")) and i["max_seconds"] > 0, "finite checkpoint interval required")
    interval(recovery.get("checkpoint_policy"))
    usage(s.get("usage"))
    for k in ("max_work_units", "max_elapsed_seconds"):
        need(finite(s["limits"].get(k)) and s["limits"][k] > 0, "finite " + k + " required")
    need(isinstance(s.get("tracked_files"), list), "tracked_files required")
    refs = set()
    for f in s["tracked_files"]:
        need(isinstance(f, dict), "invalid tracked file")
        ref = f.get("ref")
        need(isinstance(ref, str) and ref and not ref.startswith("/") and ".." not in ref.split("/") and "\\" not in ref and ":" not in ref, "unsafe tracked ref")
        need(ref not in refs, "duplicate tracked ref")
        refs.add(ref)
        need(re.fullmatch(r"[a-f0-9]{64}", f.get("sha256", "")) is not None, "tracked sha256 required")
        need(f.get("role") in {"input", "output", "evidence", "context"}, "invalid file role")
        need(f.get("graph_version") == s["graph_version"], "tracked file version mismatch")
    need(isinstance(s.get("external_requirements"), list), "external_requirements required")
    for item in s["external_requirements"]:
        need(isinstance(item, dict) and all(isinstance(item.get(k), str) and item[k] for k in ("ref", "kind", "reason")) and strings(item.get("required_for"), True), "invalid external requirement")
    if life["status"] == "completed":
        need(all(n["status"] in {"succeeded", "skipped"} for n in s["nodes"]), "completed lifecycle has unfinished nodes")
    for n in s["nodes"]:
        need(n.get("phase") in {"entry", "work", "verify", "repair", "suspended", "done"}, "invalid node phase")
        need(type(n.get("committed_step")) is int and n["committed_step"] >= 0, "invalid safe cursor")
        need(isinstance(n.get("next_safe_action"), str) and n["next_safe_action"], "next safe action required")
        need(strings(n.get("pending_steps")), "pending steps required")
        interval(n.get("checkpoint_interval")); usage(n.get("usage"))
        need(n.get("error") is None or isinstance(n["error"], dict), "invalid error")
        if n["status"] == "paused":
            need(n.get("resume_status") in {"running", "verifying", "ready"}, "paused resume_status required")
            need(life["status"] in {"pause_requested", "paused", "interrupted", "cancelled"}, "paused node in active task")
        need(isinstance(n.get("operations"), list), "operations required")
        ids = set()
        for op in n["operations"]:
            need(isinstance(op, dict) and isinstance(op.get("id"), str) and op["id"] and op["id"] not in ids, "operation ID required/unique")
            ids.add(op["id"])
            need(op.get("status") in {"prepared", "sent", "unknown", "confirmed", "not_applied", "cancelled"}, "invalid operation status")
            need(op.get("kind") in {"read", "idempotent", "non_idempotent"}, "invalid operation kind")
            need(isinstance(op.get("provider_ref"), str) and op["provider_ref"], "provider reference required")


def cell(value):
    # Prevent task data from breaking Markdown tables or creating raw HTML.
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\n", " ").replace("\r", " ")


def reference(ref):
    label = cell(ref).replace("[", "\\[").replace("]", "\\]")
    if urlsplit(ref).scheme not in {"", "http", "https"}:
        return label
    return f"[{label}]({quote(ref, safe='/:?#=&')})"


def render(s):
    validate(s)
    lines = [f"Graph `{s['graph_id']}` · version {s['graph_version']} · revision {s['revision']}", "", "| Node | Owner | State | Dependencies | Evidence (kind/verdict) | Risk / next step |", "|---|---|---|---|---|---|"]
    if s.get("schema_version") == 2:
        lines.insert(1, "Lifecycle: " + cell(s["lifecycle"]["status"]) + "; authority: " + cell(s["recovery"]["authority_location"]))
    for n in s["nodes"]:
        evidence = "; ".join(f"{reference(e['ref'])} ({e['kind']}/{e['verdict']}, v{e['graph_version']})" for e in n["evidence"]) or "none"
        nxt = n.get("reason", "") + ("; resume: " + n["resume_when"] if n.get("resume_when") else "")
        nxt = nxt or n.get("next_safe_action", n.get("next_step", "see node loop and dependency state"))
        values = [n["id"], n["owner"], n["status"], ", ".join(n["depends_on"]) or "—", evidence, nxt]
        lines.append("| " + " | ".join(cell(x) for x in values) + " |")
    # Stable numeric Mermaid identifiers avoid parser keywords and user text injection.
    indexes = {n["id"]: f"n{i}" for i, n in enumerate(s["nodes"])}
    lines += ["", "```mermaid", "flowchart TD"]
    for n in s["nodes"]:
        lines.append(f'  {indexes[n["id"]]}["{n["id"]}: {n["status"]}"]')
        for dep in n["depends_on"]:
            lines.append(f'  {indexes[dep]} --> {indexes[n["id"]]}')
    lines += ["```", "", "Snapshot validation does not prove output correctness, permissions, transition history or deadline enforcement."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--check", action="store_true", help="validate only")
    args = parser.parse_args()
    try:
        state = validate(json.loads(args.state.read_text(encoding="utf-8")))
        print("VALID snapshot" if args.check else render(state), end="\n" if args.check else "")
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
