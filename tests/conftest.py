"""pytest configuration and shared fixtures.

On Linux/WSL the soundcard library tries to load libpulse.so at import time.
That shared library is not available in headless / CI environments, so we
inject a lightweight stub into sys.modules before any test file is collected.
This mirrors the intent of the per-test patch("audio.recorder.sc.*") calls —
those patches work at class-attribute level once the module is already loaded;
this conftest ensures the module can be loaded in the first place.
"""

import sys
import types
from unittest.mock import MagicMock


def _stub_soundcard() -> None:
    """Register a minimal soundcard stub in sys.modules if libpulse is absent."""
    try:
        import soundcard  # noqa: F401 — check whether real library loads cleanly

        return  # Real library available, nothing to do.
    except OSError:
        pass

    stub = types.ModuleType("soundcard")
    stub.get_microphone = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    stub.default_speaker = MagicMock(return_value=MagicMock(name="stub-speaker"))  # type: ignore[attr-defined]
    sys.modules["soundcard"] = stub


_stub_soundcard()
