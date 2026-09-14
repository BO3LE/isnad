"""C0 · contracts — the shared language.

Every type that crosses a component boundary is defined here once, and both sides
import it. This package depends on pydantic and the standard library only.

Changing anything in this package needs two approvals (see CONTRIBUTING.md).
"""

__version__ = "0.1.0"
