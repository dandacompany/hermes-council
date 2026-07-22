"""Expose this flat plugin root as the `council` package for the test suite.

When Hermes installs the plugin it lives in a directory literally named
`council/`, so `from . import ...` and `council.register` resolve naturally.
In this repo the plugin files sit at the root, so we load `__init__.py` here as
the `council` package (with this dir as its submodule search path) — leaving
tests (`from council import ...`) and the modules' relative imports unchanged.
"""
import importlib.util, sys, pathlib

_root = pathlib.Path(__file__).parent.resolve()
if "council" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "council", _root / "__init__.py",
        submodule_search_locations=[str(_root)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["council"] = mod
    spec.loader.exec_module(mod)
