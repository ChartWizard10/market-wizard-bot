"""Market Wizard Bot — production scanner package.

Package-level ``setup_family_compiler`` is the CFR-2 production facade.  The
raw SFC-1 module remains available explicitly as ``src.setup_family_compiler``
for deterministic compiler tests and direct low-level inspection.
"""

from . import setup_family_runtime as setup_family_compiler
