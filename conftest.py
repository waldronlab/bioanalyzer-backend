"""
Root-level pytest conftest.

sys.path/PYTHONPATH setup for the `app` package is handled by
tests/conftest.py's _ensure_paths()/_ensure_app_importable() (which pytest
loads as soon as it starts collecting, since pytest.ini sets
`testpaths = tests`), together with pytest.ini's own `pythonpath = .`
option - both already cover what this file used to do by hand.

This file is intentionally left in place as a no-op rather than removed
outright: a root-level conftest.py can affect pytest's plugin/fixture
discovery scope in ways a tests/-level one does not.
"""
