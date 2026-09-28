"""gti-copilot: read-only OBD-II dashboard, radar/GPS fusion, dashcam and offline co-pilot."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gti-copilot")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
