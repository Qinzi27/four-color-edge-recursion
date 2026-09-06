"""Executable foundations for edge-side signatures and four-color experiments.

The package contains exact finite algorithms and a restricted flow-repair
dynamic program.  It does not claim a new proof of the Four Color Theorem.
Colors are integers 0..3, interpreted as the two-bit group Z2 x Z2.
"""

from .embedding import PlaneMap, vertex_defects

__all__ = ["PlaneMap", "vertex_defects"]
__version__ = "0.1.0"
