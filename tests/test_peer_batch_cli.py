"""Check the standalone entry point separately from corpus experiment results."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from scripts.name_peer_batch_map import ROOT, main, reject_nonfinite, run_document


class PeerBatchCliTests(unittest.TestCase):
    """Input annotations, interval labels and evidence preservation stay explicit."""

    def test_example_has_five_peers_and_verified_interval_names(self):
        """The runnable example has one second-stage batch, not five generations."""
        source = ROOT / "examples/peer-batch-five-lines.json"
        report = run_document(json.loads(source.read_text(encoding="utf-8")))
        self.assertEqual(report["outcome"]["status"], "solved")
        self.assertTrue(report["verification"]["passed"])
        batch = next(row for row in report["outcome"]["batch_geometry"]["stages"] if row["stage"] == 2)
        self.assertEqual(len(batch["new_mothers"]), 5)
        self.assertEqual(len(batch["coarse_cells"]), 7)  # Six inside plus outside.
        colors = report["outcome"]["colors"]
        for mother in report["final_line_profiles"]:
            for span in mother["intervals"]:
                self.assertEqual(span["left_name"], colors[span["left_side"]])
                self.assertEqual(span["right_name"], colors[span["right_side"]])

    def test_old_annotations_are_not_algorithm_inputs(self):
        """Adding an incorrect alleged coloring cannot change a fresh run."""
        document = {"strokes": [{"a": [450, 0], "b": [450, 600]}]}
        clean = run_document(document)
        marked = run_document({**document, "colors": [99], "levels": {"fake": -1}})
        self.assertEqual(clean["outcome"], marked["outcome"])
        self.assertEqual(marked["ignored_top_level_fields"], ["colors", "levels"])
        self.assertFalse(marked["old_colors_read"])

    def test_output_is_new_and_input_remains_unchanged(self):
        """A successful certificate cannot be overwritten by a second run."""
        source = ROOT / "examples/peer-batch-five-lines.json"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.json"
            with redirect_stdout(StringIO()):
                self.assertEqual(main([str(source), "--output", str(target)]), 0)
            saved = target.read_bytes()
            with self.assertRaises(SystemExit):
                main([str(source), "--output", str(target)])
            self.assertEqual(target.read_bytes(), saved)
        self.assertEqual(source.read_bytes(), before)

    def test_malformed_and_nonfinite_inputs_are_rejected(self):
        """Malformed coordinates are not a mathematical coloring obstruction."""
        for source in ([], {}, {"strokes": "not a list"}):
            with self.assertRaises(ValueError):
                run_document(source)
        with self.assertRaises(ValueError):
            reject_nonfinite("NaN")
        with self.assertRaises(ValueError):
            run_document({"frame": {"width": 30, "height": 20}, "strokes": []})


if __name__ == "__main__":
    unittest.main()
