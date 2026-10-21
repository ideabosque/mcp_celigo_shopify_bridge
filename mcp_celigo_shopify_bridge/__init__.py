#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP Celigo Bridge — Celigo integrator.io MCP tools for SilvaEngine."""

from __future__ import annotations

__author__ = "Idea Bosque"
__version__ = "0.1.0"

from .mcp_celigo_shopify_bridge import MCPCeligoBridge
from .mcp_configuration import MCP_CONFIGURATION

__all__ = ["MCPCeligoBridge", "MCP_CONFIGURATION"]