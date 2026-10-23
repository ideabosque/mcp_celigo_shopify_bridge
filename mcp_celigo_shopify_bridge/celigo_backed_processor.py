#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Base processor providing Celigo JSON-RPC execution for all mixins."""

from __future__ import annotations

__author__ = "Idea Bosque"

import logging
from typing import Any, Dict

from .celigo_client import CeligoClient


class CeligoBackedProcessor:
    """Root base class for all MCP Celigo Bridge mixins.

    Provides ``self.logger``, ``self.setting``, ``self.celigo_client``,
    and the ``_execute_celigo_call`` method that every mixin uses to
    communicate with the Celigo integrator.io MCP endpoint.
    """

    def __init__(self, logger: logging.Logger, **setting: Dict[str, Any]):
        self.logger = logger
        self.setting = setting
        self.celigo_client = CeligoClient(logger, **setting)

    @property
    def endpoint_id(self) -> str | None:
        return self.celigo_client.endpoint_id

    @endpoint_id.setter
    def endpoint_id(self, value: str):
        self.celigo_client.endpoint_id = value

    @property
    def part_id(self) -> str | None:
        return self.celigo_client.part_id

    @part_id.setter
    def part_id(self, value: str):
        self.celigo_client.part_id = value

    def _execute_celigo_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        return self.celigo_client.call_tool(tool_name, arguments)

    def _execute_order_lookup(
        self,
        payload: Dict[str, Any] | None = None,
    ) -> Any:
        """Delegate an order lookup POST to the CeligoClient REST route."""
        return self.celigo_client.lookup_orders(payload)

    def _execute_return_creation(
        self,
        payload: Dict[str, Any],
    ) -> Any:
        """Delegate a return-creation POST to the CeligoClient REST route."""
        return self.celigo_client.create_return(payload)