import pytest

from quality_ratchet.collectors.base import require_tool
from quality_ratchet.errors import CollectorError


def test_require_tool_missing_has_install_hint():
    with pytest.raises(CollectorError, match="definitely-not-a-tool-xyz not found: pip install nothing"):
        require_tool("definitely-not-a-tool-xyz", "pip install nothing")


def test_require_tool_present():
    assert require_tool("python3", "n/a").endswith("python3")
