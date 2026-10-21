#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP Celigo Bridge — Celigo integrator.io MCP Server Facade.

Typed domain mixins (policy, catalog) expose the verified remote tools as
first-class MCP tools; the ToolMixin keeps a generic escape hatch for any
tool the proxy adds.
"""

from __future__ import annotations

__author__ = "Idea Bosque"

import logging
from typing import Any, Dict

from .celigo_backed_processor import CeligoBackedProcessor
from .catalog_mixin import CatalogMixin
from .policy_mixin import PolicyMixin
from .tool_mixin import ToolMixin


class MCPCeligoBridge(
    CatalogMixin,
    PolicyMixin,
    ToolMixin,
):
    """Public interface aggregating all Celigo integrator.io MCP tools.

    Each mixin contributes its own MCP tool methods and only accesses
    ``self.logger``, ``self.setting``, and ``self._execute_celigo_call``
    (all provided by CeligoBackedProcessor). Inter-mixin calls resolve
    automatically via Python MRO on the facade instance.
    """

    def __init__(self, logger: logging.Logger, **setting: Dict[str, Any]):
        # Explicitly call the root base class to initialise logger, setting,
        # and celigo_client exactly once — mixins only reference these attrs.
        CeligoBackedProcessor.__init__(self, logger, **setting)