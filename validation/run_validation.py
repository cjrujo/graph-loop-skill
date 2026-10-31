#!/usr/bin/env python3
"""Deterministic file-task fixtures, not a model evaluation or production scheduler."""
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE / "graph-loop"
RESULTS = BASE / "validation" / "runs"
spec = importlib.util.spec_from_file_location("inspector", SKILL / "scripts" / "inspect_state.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def new_state(graph_id="example"):
    s = json.loads((BASE / "validation" / "fixtures" / "legacy-state-template.json").read_text())
    s["graph_id"] = graph_id
    s["objective"] = "Execute a deterministic local validation fixture"
    s["acceptance"] = ["Compare actual file contents against independently specified expected values"]
    s["authorization"] = ["THE-29 local validation; temporary/task-local files only; no external writes or agents"]
    s["limits"]["deadline_utc"] = "2099-01-01T00:00:00Z"  # fixture horizon, not a live task limit
    s["nodes"] = []
    return s


def node(node_id, deps=(), outputs=()):
    n = json.loads((BASE / "validation" / "fixtures" / "legacy-state-template.json").read_text())["nodes"][0]
    n.update(id=node_id, owner="single-agent-fixture", task=f"Fixture work: {node_id}", depends_on=list(deps), outputs=list(outputs))
    n["loop"]["max_no_progress"] = 2
    return n


def success(s, n, outdir, output_ref, content, expected):
    """Fixture's explicit successful work step with a content-level acceptance check."""
    n["status"] = "ready"
    checkpoint(s, outdir)
    n["attempts"] += 1
    n["status"] = "running"
    checkpoint(s, outdir)
    (outdir / output_ref).write_text(content, encoding="utf-8")
    n["status"] = "verifying"
    checkpoint(s, outdir)
    actual = (outdir / output_ref).read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError((actual, expected))
    n["artifacts"] = [{"ref": output_ref, "validity": "current", "graph_version": s["graph_version"], "sha256": hashlib.sha256(actual.encode()).hexdigest()}]
    check_ref = n["id"] + "-check.json"
    (outdir / check_ref).write_text(json.dumps({"method": "read file and compare to explicit expected content", "expected": expected, "actual": actual, "pass": True}, indent=2))
    n["evidence"].append({"ref": check_ref, "kind": "execution", "verdict": "pass", "graph_version": s["graph_version"]})
    n["status"] = "succeeded"
    n["no_progress"] = 0
    checkpoint(s, outdir)


def checkpoint(s, folder):
    """Test-fixture persistence only; helper does not implement these writes."""
    inspector.validate(s)
    s["revision"] += 1
    target = folder / "state.json"
    temp = folder / "state.tmp"
    temp.write_text(json.dumps(s, indent=2) + "\n")
    temp.replace(target)
    (folder / f"snapshot-{s['revision']:03}.json").write_text(target.read_text())
    (folder / "view.md").write_text(inspector.render(s))


class Validation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def save_run(self, name):
        target = RESULTS / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(self.folder, target)

    def rejects(self, state, fragment):
        with self.assertRaisesRegex(inspector.InvalidState, fragment):
            inspector.validate(state)

    def basic(self):
        s = new_state()
        s["nodes"] = [node("a")]
        return s, s["nodes"][0]

    def test_01_simple_real_text_task(self):
        s = new_state("simple")
        n = node("normalize", outputs=["sorted.txt"])
        s["nodes"] = [n]
        raw = " beta \n alpha\n gamma \n"
        (self.folder / "input.txt").write_text(raw)
        output = "\n".join(sorted(line.strip() for line in (self.folder / "input.txt").read_text().splitlines())) + "\n"
        success(s, n, self.folder, "sorted.txt", output, "alpha\nbeta\ngamma\n")
        self.assertEqual(n["attempts"], 1)
        self.save_run("simple")

    def test_02_parallel_file_work_and_join(self):
        s = new_state("parallel-join")
        s["limits"]["max_parallel"] = 2
        prepare = node("prepare", outputs=["data.csv"])
        stats = node("stats", ["prepare"], ["stats.json"])
        groups = node("groups", ["prepare"], ["groups.json"])
        report = node("report", ["stats", "groups"], ["report.md"])
        s["nodes"] = [prepare, stats, groups, report]
        csv_text = "group,value\nA,2\nB,4\nA,6\nB,8\n"
        success(s, prepare, self.folder, "data.csv", csv_text, csv_text)
        rows = list(csv.DictReader(io.StringIO((self.folder / "data.csv").read_text())))
        for n in (stats, groups):
            n.update(status="running", attempts=1)
        checkpoint(s, self.folder)
        report["status"] = "ready"
        self.rejects(s, "dependency not satisfied")
        report["status"] = "pending"
        barrier = threading.Barrier(2, timeout=5)

        def statistics():
            barrier.wait()
            values = [int(r["value"]) for r in rows]
            data = {"count": len(values), "total": sum(values), "mean": sum(values) / len(values)}
            (self.folder / "stats.json").write_text(json.dumps(data, sort_keys=True))
            return data

        def grouping():
            barrier.wait()
            data = {key: sum(r["group"] == key for r in rows) for key in sorted({r["group"] for r in rows})}
            (self.folder / "groups.json").write_text(json.dumps(data, sort_keys=True))
            return data

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(statistics), pool.submit(grouping)
            self.assertEqual(a.result(timeout=10), {"count": 4, "total": 20, "mean": 5.0})
            self.assertEqual(b.result(timeout=10), {"A": 2, "B": 2})
        for n, ref, expected in ((stats, "stats.json", {"count": 4, "total": 20, "mean": 5.0}), (groups, "groups.json", {"A": 2, "B": 2})):
            n["status"] = "verifying"
            checkpoint(s, self.folder)
            self.assertEqual(json.loads((self.folder / ref).read_text()), expected)
            check_ref = n["id"] + "-check.json"
            (self.folder / check_ref).write_text(json.dumps({"expected": expected, "actual": json.loads((self.folder / ref).read_text()), "pass": True}))
            n.update(status="succeeded", artifacts=[{"ref": ref, "validity": "current", "graph_version": 1}], evidence=[{"ref": check_ref, "kind": "execution", "verdict": "pass", "graph_version": 1}])
            checkpoint(s, self.folder)
        data = json.loads((self.folder / "stats.json").read_text())
        grouped = json.loads((self.folder / "groups.json").read_text())
        content = f"count={data['count']}; total={data['total']}; mean={data['mean']}; groups={grouped}\n"
        success(s, report, self.folder, "report.md", content, "count=4; total=20; mean=5.0; groups={'A': 2, 'B': 2}\n")
        self.save_run("parallel-join")

    def test_03_retry_then_blocked_checkpoint_recovery(self):
        s = new_state("retry-recover")
        producer = node("produce", outputs=["number.txt"])
        consumer = node("consume", ["produce"], ["result.txt"])
        s["nodes"] = [producer, consumer]
        producer.update(status="running", attempts=1)
        checkpoint(s, self.folder)
        (self.folder / "number.txt").write_text("ten")
        producer["status"] = "verifying"
        checkpoint(s, self.folder)
        with self.assertRaises(ValueError):
            int((self.folder / "number.txt").read_text())
        (self.folder / "failed-check.txt").write_text("int('ten') raised ValueError; use numeric serialization")
        producer.update(status="failed", reason="Numeric parser rejected English text; changed repair: write decimal digits", no_progress=0)
        producer["evidence"] = [{"ref": "failed-check.txt", "kind": "execution", "verdict": "fail", "graph_version": 1}]
        checkpoint(s, self.folder)
        success(s, producer, self.folder, "number.txt", str(10), "10")
        self.assertEqual(producer["attempts"], 2)
        consumer.update(status="blocked", reason="multiplier.txt absent", resume_when="local fixture provides readable multiplier.txt")
        checkpoint(s, self.folder)
        # Read-only CLI in a new process, followed by reload from durable JSON.
        cli = subprocess.run([sys.executable, str(SKILL / "scripts" / "inspect_state.py"), str(self.folder / "state.json"), "--check"], capture_output=True, text=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        s = json.loads((self.folder / "state.json").read_text())
        producer, consumer = s["nodes"]
        self.assertEqual(producer["attempts"], 2)
        self.assertEqual(consumer["attempts"], 0)
        (self.folder / "multiplier.txt").write_text("3")  # fixture change, not a fabricated human answer
        consumer["status"] = "pending"
        consumer.pop("reason")
        consumer.pop("resume_when")
        checkpoint(s, self.folder)
        value = int((self.folder / "number.txt").read_text()) * int((self.folder / "multiplier.txt").read_text())
        success(s, consumer, self.folder, "result.txt", str(value), "30")
        self.save_run("retry-recover")

    def test_04_branch_exclusion_and_join(self):
        s = new_state("branch")
        select = node("select", outputs=["route.txt"])
        small = node("small", ["select"], ["answer.txt"])
        large = node("large", ["select"], ["unused.txt"])
        small["branch"] = {"node": "select", "equals": "small"}
        large["branch"] = {"node": "select", "equals": "large"}
        join = node("join", ["small", "large"], ["joined.txt"])
        s["nodes"] = [select, small, large, join]
        select["selection"] = "small" if len([1, 2, 3]) < 5 else "large"
        success(s, select, self.folder, "route.txt", select["selection"], "small")
        large["status"] = "skipped"
        checkpoint(s, self.folder)
        success(s, small, self.folder, "answer.txt", str(sum([1, 2, 3])), "6")
        success(s, join, self.folder, "joined.txt", (self.folder / "answer.txt").read_text(), "6")
        self.assertFalse((self.folder / "unused.txt").exists())
        self.save_run("branch")

    def test_05_replan_rejects_stale_success_and_join(self):
        s = new_state("replan")
        a = node("a", outputs=["a.txt"])
        b = node("b", ["a"], ["b.txt"])
        s["nodes"] = [a, b]
        success(s, a, self.folder, "a.txt", "old-input-result", "old-input-result")
        s["graph_version"] = 2
        self.rejects(s, "old version")
        a["artifacts"][0]["validity"] = "stale"
        a["status"] = "pending"
        checkpoint(s, self.folder)
        b["status"] = "ready"
        self.rejects(s, "dependency not satisfied")
        b["status"] = "pending"
        checkpoint(s, self.folder)
        self.assertEqual(a["attempts"], 1)
        self.save_run("replan")

    def test_06_attempt_budget_cannot_be_restarted(self):
        s, n = self.basic()
        n.update(status="ready", attempts=2)
        self.rejects(s, "no attempt remains")
        n.update(status="running", attempts=3)
        self.rejects(s, "budget exceeded")

    def test_07_no_progress_stops_retry(self):
        s, n = self.basic()
        n.update(attempts=1, no_progress=1, status="ready")
        n["loop"]["max_no_progress"] = 1
        self.rejects(s, "no-progress limit")
        n.update(status="failed", reason="unchanged acceptance failure; stop")
        inspector.validate(s)

    def test_08_failure_propagation_does_not_unlock(self):
        s, a = self.basic()
        a.update(status="failed", attempts=1, reason="parse rejected input")
        b = node("b", ["a"])
        s["nodes"].append(b)
        b["status"] = "ready"
        self.rejects(s, "dependency not satisfied")
        b.update(status="blocked", reason="upstream a failed", resume_when="a succeeds with current evidence")
        inspector.validate(s)

    def test_09_not_run_is_not_pass(self):
        s, n = self.basic()
        n.update(status="succeeded", attempts=1, evidence=[{"ref": "check", "kind": "not_run", "verdict": "pass", "graph_version": 1}])
        self.rejects(s, "not_run cannot")

    def test_10_simulation_requires_declared_scope(self):
        s, n = self.basic()
        n.update(status="succeeded", attempts=1, evidence=[{"ref": "simulation-result", "kind": "simulation", "verdict": "pass", "graph_version": 1}])
        self.rejects(s, "no current passing evidence")
        n["allow_simulation"] = True
        inspector.validate(s)

    def test_11_missing_output_even_with_evidence(self):
        s, n = self.basic()
        n.update(outputs=["missing.txt"], status="succeeded", attempts=1, evidence=[{"ref": "check", "kind": "execution", "verdict": "pass", "graph_version": 1}])
        self.rejects(s, "artifact missing")

    def test_12_topology_cycle_and_unknown_dependency(self):
        s, a = self.basic()
        b = node("b", ["a"])
        s["nodes"].append(b)
        a["depends_on"] = ["b"]
        self.rejects(s, "cycle")
        a["depends_on"] = ["unknown"]
        self.rejects(s, "invalid dependency")

    def test_13_branch_cannot_hide_required_work(self):
        s, n = self.basic()
        n["status"] = "skipped"
        self.rejects(s, "skipped without branch")

    def test_14_parallel_resource_cap(self):
        s, n = self.basic()
        n.update(status="running", attempts=1)
        other = node("other")
        other.update(status="running", attempts=1)
        s["nodes"].append(other)
        self.rejects(s, "parallel cap")

    def test_15_blocker_needs_resume_condition(self):
        s, n = self.basic()
        n.update(status="blocked", reason="file missing")
        self.rejects(s, "resume_when")

    def test_16_view_uses_snapshot_and_escapes_task_text(self):
        s, n = self.basic()
        n["owner"] = "name|<tag>\nrow"
        before = copy.deepcopy(s)
        view = inspector.render(s)
        self.assertEqual(s, before)
        self.assertIn("name&#124;&lt;tag&gt; row", view)
        self.assertIn("version 1 · revision 1", view)
        n["status"] = "ready"
        self.assertIn('n0["a: ready"]', inspector.render(s))

    def test_17_cli_bad_json_and_invalid_snapshot(self):
        script = SKILL / "scripts" / "inspect_state.py"
        for content in ("not-json", "[]", '{"schema_version": 88}'):
            file = self.folder / "bad.json"
            file.write_text(content)
            p = subprocess.run([sys.executable, str(script), str(file)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            self.assertTrue(p.stderr.startswith("INVALID:"))

    def test_18_project_copy_integrity_and_collision(self):
        target = self.folder / ".agents" / "skills" / "graph-loop"
        shutil.copytree(SKILL, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for file in SKILL.rglob("*"):
            if file.is_file() and "__pycache__" not in file.parts:
                self.assertEqual(file.read_bytes(), (target / file.relative_to(SKILL)).read_bytes())
        before = (target / "SKILL.md").read_bytes()
        with self.assertRaises(FileExistsError):
            shutil.copytree(SKILL, target)
        self.assertEqual((target / "SKILL.md").read_bytes(), before)
        p = subprocess.run([sys.executable, str(target / "scripts" / "inspect_state.py"), str(target / "assets" / "state-template.json"), "--check"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        # This tests copying and relative resources, never native host discovery.

    def test_19_duplicate_nodes_and_nonfinite_budgets(self):
        s, n = self.basic()
        s["nodes"].append(copy.deepcopy(n))
        self.rejects(s, "duplicate node")
        s["nodes"].pop()
        n["loop"]["max_attempts"] = 0
        self.rejects(s, "finite max_attempts")

    def test_20_false_success_without_current_evidence(self):
        s, n = self.basic()
        n.update(status="succeeded", attempts=1)
        self.rejects(s, "no current passing evidence")


if __name__ == "__main__":
    RESULTS.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Validation)
    with (BASE / "validation" / "test-output.log").open("w") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    summary = {"method": "deterministic fixtures and state invariants, not model or host evaluation", "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "passed": result.testsRun - len(result.failures) - len(result.errors), "python": sys.version.split()[0], "successful": result.wasSuccessful()}
    (BASE / "validation" / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    if not result.wasSuccessful():
        print((BASE / "validation" / "test-output.log").read_text())
    sys.exit(0 if result.wasSuccessful() else 1)
