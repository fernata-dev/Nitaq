"""Convenience shim so `python -m nitaq` works from a fresh checkout (puts ./src on the path)."""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
while _SRC in sys.path:          # always first, even if PYTHONPATH already lists it later
    sys.path.remove(_SRC)
sys.path.insert(0, _SRC)

if __name__ == "__main__":
    import runpy

    runpy.run_module("nitaq", run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules.pop(__name__, None)
    sys.modules[__name__] = importlib.import_module(__name__)
