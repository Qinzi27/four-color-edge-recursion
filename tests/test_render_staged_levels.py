"""Check exact v3 figure evidence and annotation semantics without saving files."""

from copy import deepcopy
import unittest

from scripts import render_staged_levels as renderer
from scripts import validate_staged_levels_full as runner


class RecordingCanvas:
    """Record drawing instructions only, avoiding any image or file mutation."""

    def __init__(self):
        self.lines, self.labels = [], []

    def line(self, points, **style):
        """Keep exact submitted coordinates for geometric comparison."""
        self.lines.append((points, style))

    def text(self, position, label, **style):
        """Keep text semantic values independently of raster font rendering."""
        self.labels.append((position, label, style))


class StagedLevelRendererTests(unittest.TestCase):
    """No stale result, altered geometry or implicit failed coloring is accepted."""

    @classmethod
    def setUpClass(cls):
        """Recompute one predeclared archived case; this is not a full run."""
        archive = runner.read_json(runner.SOURCE)
        row = next(row for row in archive["drawings"] if row["key"] == renderer.BLUE_KEY)
        piece = runner.run_batch((0, [row], {row["key"]}))
        # Only checked_case's required in-memory fields are constructed. This
        # object deliberately does not claim full_corpus_run or get saved.
        cls.evidence = renderer.json_value({"drawings": piece["records"],
                                            "detailed_examples": piece["detailed_examples"]})
        cls.case = renderer.checked_case(cls.evidence, renderer.BLUE_KEY)

    def test_checked_case_rejects_geometry_or_result_hash_changes(self):
        """A plausible colored picture cannot replace an exact archived proof."""
        detail, row, result, check, payload = self.case
        self.assertEqual(result["status"], "solved")
        self.assertTrue(check["passed"])
        self.assertEqual(len(payload["sides"]), len(result["colors"]) - 1)
        for field in ("geometry_sha256", "raw_result_sha256"):
            with self.subTest(field=field):
                changed = deepcopy(self.evidence)
                target = changed["drawings"][0]
                if field == "geometry_sha256":
                    target[field] = "0" * 64
                else:
                    target["runs"][runner.POLICY][field] = "0" * 64
                with self.assertRaisesRegex(AssertionError, "hash changed"):
                    renderer.checked_case(changed, renderer.BLUE_KEY)

    def test_blue_outline_matches_only_selected_side_existing_bounds(self):
        """The annotation cannot create a new dividing line or move a thin band."""
        _, _, result, _, payload = self.case
        canvas = RecordingCanvas()
        renderer.highlight_retained(canvas, payload, result["initialization"])
        self.assertEqual(len(canvas.lines), 1)
        bounds = next(side["bounds"] for side in payload["sides"]
                      if int(side["id"]) == result["initialization"]["side"])
        x0, y0, x1, y1 = bounds
        expected = [(renderer.ORIGIN[0] + x * renderer.SCALE,
                     renderer.ORIGIN[1] + y * renderer.SCALE)
                    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]
        self.assertEqual(canvas.lines[0][0], expected)

    def test_failure_side_table_has_ids_but_no_completed_color_claim(self):
        """Blank diagrams retain every side ID while withholding final names."""
        payload = self.case[-1]
        canvas = RecordingCanvas()
        renderer.side_table(canvas, payload, blank=True)
        labels = [label for _, label, _ in canvas.labels[1:]]
        self.assertEqual(labels, [f"s{side['id']} → ?" for side in payload["sides"]])
        colored = RecordingCanvas()
        renderer.side_table(colored, payload, blank=False)
        self.assertEqual([label for _, label, _ in colored.labels[1:]],
                         [f"s{side['id']} → {side['symbol']}" for side in payload["sides"]])


if __name__ == "__main__":
    unittest.main()
