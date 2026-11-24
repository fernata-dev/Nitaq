"""Convenience shim: lets `python -m nitaq_bench ...` (and `import nitaq_bench`) work from a
fresh checkout without `pip install -e .`.  It only puts ./src first on
sys.path and hands over to the real package in src/nitaq_bench.  No project logic
lives here."""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
while _SRC in sys.path:          # always first, even if PYTHONPATH already lists it later
    sys.path.remove(_SRC)
sys.path.insert(0, _SRC)

if __name__ == "__main__":
    import runpy

    runpy.run_module("nitaq_bench", run_name="__main__", alter_sys=True)
else:
    import importlib

    sys.modules.pop(__name__, None)
    sys.modules[__name__] = importlib.import_module(__name__)
