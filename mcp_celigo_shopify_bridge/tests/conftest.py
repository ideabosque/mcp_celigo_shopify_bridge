#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pytest configuration and fixtures for MCP Celigo Bridge tests."""
from __future__ import annotations

__author__ = "Idea Bosque"

import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

# Setup logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("test_mcp_celigo_shopify_bridge")

# Make package importable — project root (parent of the mcp_celigo_shopify_bridge package dir)
base_dir = os.getenv("base_dir", os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, base_dir)

from mcp_celigo_shopify_bridge.mcp_celigo_shopify_bridge import MCPCeligoBridge


# Minimal setting dict — celigo_mcp config is required by CeligoClient
# but for unit tests we mock _execute_celigo_call so it's not used.
SETTING = {
    "celigo_mcp": {
        "endpoint": "https://api.integrator.io/apis/v1/api/ucp/mcp",
        "legacy_endpoint": "https://api.integrator.io/apis/v1/api/mcp",
        "bearer_token": "mock-bearer-token",
    }
}


@pytest.fixture
def processor():
    """Provide an MCPCeligoBridge instance with mocked Celigo execution.

    The _execute_celigo_call method is replaced with a MagicMock so
    each test can configure its return value independently.
    """
    proc = MCPCeligoBridge(logger, **SETTING)
    proc.endpoint_id = "test-endpoint-id"
    proc.part_id = "test-part-id"
    proc._execute_celigo_call = MagicMock()
    return proc


@pytest.fixture
def celigo_result_factory():
    """Factory fixture to build raw Celigo client return values.

    Usage::

        processor._execute_celigo_call.return_value = celigo_result_factory(
            [{"question": "...", "answer": "..."}]
        )
    """

    def _make(data):
        return data

    return _make


@pytest.fixture
def gql_result_factory(celigo_result_factory):
    """Alias kept for symmetry with other MCP bridge test suites."""
    return celigo_result_factory