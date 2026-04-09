"""
测试配置

提供测试所需的 fixtures 和配置。
"""
import sys
import os
from pathlib import Path

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_binance_config():
    """模拟 Binance 配置"""
    os.environ["BINANCE_TESTNET_API_KEY"] = "test_key"
    os.environ["BINANCE_TESTNET_API_SECRET"] = "test_secret"
    return True


@pytest.fixture
def mock_env_vars():
    """设置必要的环境变量"""
    os.environ.setdefault("BINANCE_TESTNET_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_TESTNET_API_SECRET", "test_secret")
    os.environ.setdefault("LLM_MODEL", "glm_4_7")
