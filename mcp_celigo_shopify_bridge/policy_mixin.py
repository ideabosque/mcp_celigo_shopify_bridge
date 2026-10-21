#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shop policies and FAQs mixin for MCP Celigo Bridge."""

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


class PolicyMixin(CeligoBackedProcessor):

    @handle_errors(operation_name="search_shop_policies_and_faqs")
    def search_shop_policies_and_faqs(
        self, **arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        query = arguments.get("query")
        validate_not_empty(
            query.strip() if isinstance(query, str) else query, "query"
        )
        query = query.strip() if isinstance(query, str) else query

        tool_arguments = {"query": query}
        limit = arguments.get("limit")
        if limit is not None:
            tool_arguments["limit"] = int(limit)
        tool_arguments = {
            k: v for k, v in tool_arguments.items() if v is not None and v != ""
        }

        tool_name = "search_shop_policies_and_faqs"
        result = self._execute_celigo_call(tool_name, tool_arguments)
        if error := propagate_error_if_present(result):
            return error

        data = humps.decamelize(result) if isinstance(result, (dict, list)) else result

        if is_empty_result(data):
            return "No shop policies or FAQs found for this query."

        return data