"""Shared library for the Enterprise AWS Landing Zone automation toolkit.

Modules
-------
eawlz_core
    Pure, dependency-free functions used by every CLI script and by the test
    suite. Keeping logic here (instead of inside the CLIs) is what makes the
    tooling unit-testable without AWS, Terraform state, or network access.
"""

__all__ = ["eawlz_core"]
__version__ = "1.0.0"
