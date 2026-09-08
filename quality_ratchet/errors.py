class CollectorError(RuntimeError):
    """A collector could not produce its metrics (tool missing, tool failed)."""


class ConfigError(RuntimeError):
    """Config or baseline are inconsistent."""
