"""Check the drawing adapter and non-destructive certificate output contract."""

from pathlib import Path
import tempfile
import unittest

from scripts.name_joint_boundary_map import main, run_document


class JointBoundaryCliTests(unittest.TestCase):
    """Use a tiny drawing; the full corpus audit covers complex trajectories."""

    def test_supplied_old_names_are_ignored_and_proof_is_verified(self):
        """Only frame and strokes enter geometry and the naming algorithm."""
        document = {"strokes": [{"a": [0, 300], "b": [900, 300]}], "old_colors": [99]}
        result = run_document(document, "joint")
        self.assertEqual(result["outcome"]["status"], "solved")
        self.assertTrue(result["verification"]["passed"])
        self.assertEqual(result["ignored_top_level_fields"], ["old_colors"])
        self.assertEqual(result["production_attempts"], 1)
        self.assertFalse(result["outcome"]["old_colors_read"])

    def test_existing_output_cannot_be_overwritten(self):
        """Output preservation precedes even opening a missing input path."""
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "existing.json"
            target.write_text("original evidence", encoding="utf-8")
            with self.assertRaises(SystemExit) as stopped:
                main([str(Path(folder) / "missing.json"), "--mode", "joint", "--output", str(target)])
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "original evidence")


if __name__ == "__main__":
    unittest.main()
