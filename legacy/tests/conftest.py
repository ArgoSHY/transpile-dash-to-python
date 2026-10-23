"""Shared setup for the trans.py behaviour-snapshot suite.

These tests are pure characterisation ("golden") tests:

* every test builds a real ``trans.Transpiler`` and calls one of its methods;
* nothing is mocked, stubbed, patched or monkeypatched;
* each assertion pins the exact string / tuple that the implementation returns
  for a given input today.

The suite intentionally records the *current* behaviour, including known
quirks.  Cases marked "CURRENT QUIRK" or "KNOWN BUG" document output that a
rewrite should probably not preserve; when a quirk is fixed, update that
snapshot deliberately instead of silently deleting the test.
"""

import sys
from pathlib import Path

import pytest

# trans.py is a stand-alone script, not an installed package: make the project
# root importable so the tests can run from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trans import Transpiler  # noqa: E402  (import after sys.path tweak)


@pytest.fixture(scope="session")
def transpiler() -> Transpiler:
    """A shared, stateless Transpiler instance (no mocking involved)."""
    return Transpiler()
