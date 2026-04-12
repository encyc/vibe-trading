"""
Pytest configuration for Vibe Trading tests
"""
import asyncio
import sys
import os
from pathlib import Path

# Add backend/src to Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "backend" / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


# pytest-asyncio configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "asyncio: mark test as an async test"
    )


# Auto-apply asyncio marker to all async test functions
def pytest_collection_modifyitems(session, config, items):
    """
    Automatically apply @pytest.mark.asyncio to async test functions
    """
    for item in items:
        if asyncio.iscoroutinefunction(item.obj):
            item.add_marker("asyncio")
