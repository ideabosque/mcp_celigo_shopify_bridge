#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live integration runner for MCP Celigo Shopify Bridge.

Invokes a Celigo integrator.io MCP tool (name is a variable) against the
real endpoint. Credentials come from mcp_celigo_shopify_bridge/tests/.env (see
.env.example). This script mutates nothing — the default probe is a
read-only search.

Usage:
    python -m mcp_celigo_shopify_bridge.tests.run_integration
"""
from __future__ import annotations

__author__ = "Idea Bosque"

import json
import os
import sys
from datetime import datetime, timezone

base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, base_dir)

from mcp_celigo_shopify_bridge.mcp_celigo_shopify_bridge import MCPCeligoBridge

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env() -> dict:
    env_path = os.path.join(TESTS_DIR, ".env")
    values = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    # Environment variables take precedence over the .env file.
    for key in (
        "CELIGO_MCP_ENDPOINT",
        "CELIGO_LEGACY_ENDPOINT",
        "CELIGO_BEARER_TOKEN",
        "CELIGO_TOOL_NAME",
        "CELIGO_TOOL_ARGUMENTS",
    ):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def main() -> int:
    env = _load_env()
    token = env.get("CELIGO_BEARER_TOKEN")
    if not token or token == "replace-me":
        print("SKIP: CELIGO_BEARER_TOKEN not configured (see tests/.env.example)")
        return 0

    import logging

    logger = logging.getLogger("celigo_integration")
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    setting = {
        "celigo_mcp": {
            "endpoint": env.get(
                "CELIGO_MCP_ENDPOINT",
                "https://api.integrator.io/apis/v1/api/ucp/mcp",
            ),
            "legacy_endpoint": env.get(
                "CELIGO_LEGACY_ENDPOINT",
                "https://api.integrator.io/apis/v1/api/mcp",
            ),
            "bearer_token": token,
        }
    }
    processor = MCPCeligoBridge(logger, **setting)

    tool_name = env.get("CELIGO_TOOL_NAME", "search_shop_policies_and_faqs")
    arguments_raw = env.get(
        "CELIGO_TOOL_ARGUMENTS",
        json.dumps({"query": "what is your shipping policy"}),
    )
    try:
        arguments = json.loads(arguments_raw)
    except Exception:
        print(f"FAIL: CELIGO_TOOL_ARGUMENTS is not valid JSON: {arguments_raw}")
        return 1

    print(f"Tool: {tool_name} | Arguments: {arguments}")
    result = processor.call_celigo_tool(name=tool_name, arguments=arguments)

    if isinstance(result, dict) and "error" in result:
        print(f"FAIL: {json.dumps(result, indent=2)}")
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(
        f"PASS at {datetime.now().isoformat()}: "
        f"{len(result) if isinstance(result, list) else 1} record(s) returned"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())