"""Reconstruct web certificates using the separately implemented Python core.

Node only emits data; Python independently traverses darts and integrates labels.
This validates finite examples, not all maps or the completeness of greedy selection.
"""
from __future__ import annotations
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.embedding import PlaneMap, vertex_defects  # noqa: E402


def main() -> None:
    """Fail on any cross-language disagreement; save a portable summary."""
    completed = subprocess.run(
        ["node", "scripts/export-web-cases.mjs"], cwd=ROOT,
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    data = json.loads(completed.stdout)
    records = []
    for item in data["records"]:
        result = item["result"]
        plane = PlaneMap(
            tuple((str(edge["a"]), str(edge["b"])) for edge in result["edges"]),
            {str(i): tuple(darts) for i, darts in enumerate(result["rotation"])},
        )
        assert plane.face_of_dart == tuple(result["faceOfDart"]), item["id"]
        assert plane.faces == tuple(tuple(face) for face in result["faces"])
        colors = result["colors"]
        solved = result["selection"]["status"] == "solved"
        if solved:
            assert plane.check_coloring(colors)
            differences = plane.differences(colors)
            assert differences == tuple(result["verification"]["differences"])
            assert all(value == 0 for value in vertex_defects(plane, differences).values())
            integrated = plane.integrate(differences)
            assert integrated == tuple(color ^ colors[0] for color in colors)
        else:
            assert result["selection"]["status"] == "blocked"
            assert result["verification"] is None
            for edge_id in range(len(plane.edges)):
                left, right = plane.shores(edge_id)
                if left != right and colors[left] >= 0 and colors[right] >= 0:
                    assert colors[left] != colors[right]
        trace = result["selection"]["trace"]
        assert len({step["face"] for step in trace}) == len(trace)
        assert result["selection"]["backtracks"] == 0
        records.append({"id": item["id"], "faces": len(plane.faces), "status": result["selection"]["status"], "passed": True})
    report = {
        "schema_version": 1, "seed": data["seed"], "family": data["randomFamily"],
        "python": platform.python_version(), "cases": len(records),
        "solved": sum(r["status"] == "solved" for r in records),
        "blocked": sum(r["status"] == "blocked" for r in records),
        "all_passed": True, "records": records,
        "scope": "Finite cross-language topology and certificate checks; not greedy completeness.",
        "browser_ui_tested": False, "webmcp_browser_context_verified": False,
    }
    output = ROOT / "outputs" / "web-validation.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Web/Python agreement: {len(records)} PASS; solved={report['solved']}, blocked={report['blocked']}")


if __name__ == "__main__":
    main()
