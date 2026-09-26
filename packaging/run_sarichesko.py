"""Thin PyInstaller entry point.

Must live OUTSIDE the sarichesko/ package. sarichesko/app.py uses
package-relative imports (`from .ui.main_window import ...`), which only
resolve when Python knows app.py is part of the sarichesko package. Handing
PyInstaller sarichesko/app.py directly as the Analysis script makes the
frozen build execute it as a bare top-level script with no parent package --
every relative import then fails at runtime with:
    ImportError: attempted relative import with no known parent package
Importing sarichesko.app properly (as this file does) gives it that
package context, so the frozen executable actually runs.
"""
from sarichesko.app import main

if __name__ == "__main__":
    main()