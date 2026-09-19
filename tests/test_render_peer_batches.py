"""Check truthful peer-batch figure primitives without font or file rendering."""

from copy import deepcopy
from unittest.mock import patch
import unittest

from scripts import render_peer_batches as renderer


class RecordingCanvas:
    """Record exact drawing requests, avoiding raster generation in unit tests."""

    def __init__(self, width=0, height=0, font=None):
        self.width, self.height = width, height
        self.lines, self.labels, self.rectangles, self.svg = [], [], [], []
        self.draw = self

    def line(self, points, **style):
        """Keep every original point and declared stroke style."""
        self.lines.append((points, style))

    def text(self, position, label, **style):
        """Keep semantic text rather than requiring the Windows CJK font."""
        self.labels.append((position, label, style))

    def rectangle(self, points, **style):
        """Retain fill bounds for exact-width and color-name checks."""
        self.rectangles.append((points, style))


class PeerBatchRendererTests(unittest.TestCase):
    """No rewritten geometry or old legal coloring may masquerade as v4."""

    @classmethod
    def setUpClass(cls):
        """Construct a minimal in-memory report, never mark it as a full run."""
        old = renderer.read_json(renderer.OLD_INPUT)
        detail = old["detailed_examples"][renderer.LEAST_OLD]
        geometry = detail["geometry"]
        result = renderer.restart_peer_batch_names(geometry)
        check = renderer.verify_run(geometry, result)
        cls.report = renderer.json_value({
            "drawings": [{"key": detail["key"], "geometry_sha256": renderer.digest(geometry),
                          "runs": {renderer.POLICY: {"raw_result_sha256": renderer.digest(result)}}}],
            "detailed_examples": {detail["key"]: {**detail, "outcome": result, "verification": check}},
        })
        cls.evidence = renderer.checked_case(cls.report, renderer.LEAST_OLD)

    def test_checked_illustration_rejects_stale_geometry_and_result(self):
        """Rerun hashes and full proof must match, not merely appear plausible."""
        self.assertEqual(self.evidence["result"]["status"], "solved")
        self.assertTrue(self.evidence["verification"]["passed"])
        for kind in ("geometry", "result", "proof"):
            with self.subTest(kind=kind):
                forged = deepcopy(self.report)
                if kind == "geometry":
                    forged["drawings"][0]["geometry_sha256"] = "0" * 64
                elif kind == "result":
                    forged["drawings"][0]["runs"][renderer.POLICY]["raw_result_sha256"] = "0" * 64
                else:
                    forged["detailed_examples"][renderer.LEAST_OLD]["verification"]["passed"] = False
                with self.assertRaises(AssertionError):
                    renderer.checked_case(forged, renderer.LEAST_OLD)

    def test_stage_view_activates_exact_five_lines_and_retains_all_later_mothers(self):
        """A dashed future line is visible geometry, not a removed constraint."""
        with patch.object(renderer, "Canvas", RecordingCanvas):
            canvas = renderer.coarse_stage_canvas(self.evidence, 13, "unused")
        active = [points for points, style in canvas.lines
                  if style.get("color") == renderer.LINE_ID and style.get("width") == 5]
        self.assertEqual(active, [[(50 + x * 1.2, 235), (50 + x * 1.2, 955)]
                                  for x in (190, 274, 551, 708, 817)])
        # A separate grey legend segment has width4; actual inactive mothers use2.
        future = [points for points, style in canvas.lines
                  if style.get("color") == renderer.GHOST and style.get("width") == 2]
        model = renderer.build_whole_lines(self.evidence["geometry"])
        self.assertEqual(len(future), len(model.lines) - 1 - 5)
        self.assertEqual(len(canvas.rectangles), 6)
        ready_fills = [row for row in canvas.rectangles if row[1]["fill"] == renderer.READY_FILL]
        self.assertEqual(len(ready_fills), 4)
        labels = [text for _, text, _ in canvas.labels]
        self.assertIn("s13", labels)
        self.assertTrue(any("不代表颜色2或3" in text for text in labels))

    def test_thin_side_fill_and_full_table_are_preserved_without_duplicate_label(self):
        """Tiny bands are never enlarged or dropped to improve appearance."""
        payload = {"width": 100, "height": 100, "cuts": [[[8, 0], [8, 100]]],
                   "sides": [{"id": "1", "bounds": [0, 0, 8, 100], "symbol": 1},
                             {"id": "2", "bounds": [8, 0, 100, 100], "symbol": 2}]}
        canvas = RecordingCanvas()
        renderer.exact_map(canvas, payload, (50, 70), 1.1)
        self.assertEqual(canvas.rectangles[0][0], [(50, 70), (58.8, 180)])
        self.assertEqual([text for _, text, _ in canvas.labels], ["2"])
        renderer.table(canvas, payload, (200, 70), blank=False)
        self.assertEqual([text for _, text, _ in canvas.labels][-2:], ["s1 = 1", "s2 = 2"])
        blank = RecordingCanvas()
        renderer.table(blank, payload, (200, 70), blank=True)
        self.assertEqual([text for _, text, _ in blank.labels], ["s1 = ?", "s2 = ?"])

    def test_old_fatal_outline_uses_only_existing_side_boundary(self):
        """The orange marker cannot become a new cut or merge adjacent sides."""
        side = next(item for item in self.evidence["payload"]["sides"] if item["id"] == "13")
        canvas = RecordingCanvas()
        renderer.outline(canvas, side, (55, 230), 1.1)
        x0, y0, x1, y1 = side["bounds"]
        self.assertEqual(canvas.lines[0][0], [(55 + x * 1.1, 230 + y * 1.1)
                                             for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))])


if __name__ == "__main__":
    unittest.main()
