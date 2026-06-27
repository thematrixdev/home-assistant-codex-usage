"""Verify _as_percent handles the 0-vs-1 boundary correctly."""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components"))

from hass_codex_usage import _as_percent  # noqa: E402


def test_boundary():
    # Exactly 1 means 1%, not 100%-as-fraction
    assert _as_percent(1) == 1.0
    assert _as_percent(1.0) == 1.0

    # Fractions → scaled up
    assert _as_percent(0.5) == 50.0
    assert _as_percent(0.02) == 2.0
    assert _as_percent(0.0) == 0.0   # 0 stays 0

    # Already 0-100 scale
    assert _as_percent(2) == 2.0
    assert _as_percent(50) == 50.0
    assert _as_percent(100) == 100.0

    # Edge / invalid
    assert _as_percent(-1) is None
    assert _as_percent(1001) is None
    assert _as_percent("50%") == 50.0
    assert _as_percent("bad") is None
    assert _as_percent(None) is None


if __name__ == "__main__":
    test_boundary()
    print("OK")
