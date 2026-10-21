#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generic Celigo MCP tool invocation mixin for MCP Celigo Bridge."""

from __future__ import annotations

__author__ = "Idea Bosque"

from typing import Any, Dict

import humps

from .celigo_backed_processor import CeligoBackedProcessor
from .error_handler import (
    handle_errors,
    is_empty_result,
    propagate_error_if_present,
    validate_not_empty,
)


class ToolMixin(CeligoBackedProcessor):

    @handle_errors(operation_name="call_celigo_tool")
    def call_celigo_tool(self, **arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke any Celigo integrator.io MCP tool by name.

        ``name`` is a variable supplied by the caller — the bridge forwards
        it verbatim in the JSON-RPC ``params.name`` field together with the
        tool's ``arguments`` object.
        """
        name = arguments.get("name")
        validate_not_empty(name, "name")

        tool_arguments = arguments.get("arguments")
        if tool_arguments is not None and not isinstance(tool_arguments, dict):
            from .error_handler import ValidationError, ErrorCode

            raise ValidationError(
                message="arguments must be a JSON object",
                error_code=ErrorCode.INVALID_ARGUMENTS,
                details={"field": "arguments"},
            )
        tool_arguments = {
            k: v for k, v in (tool_arguments or {}).items()
            if v is not None and v != ""
        }

        result = self._execute_celigo_call(name, tool_arguments)
        if error := propagate_error_if_present(result):
            return error

        data = humps.decamelize(result) if isinstance(result, (dict, list)) else result

        if is_empty_result(data):
            return "No results returned by Celigo tool '%s'." % name

        return data