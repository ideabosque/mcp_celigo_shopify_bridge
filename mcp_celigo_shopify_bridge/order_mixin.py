#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Order lookup mixin for MCP Celigo Bridge.

Backed by the Celigo integrator.io order REST route — a plain
``POST`` to ``https://api.integrator.io/apis/v1/api/orders`` with Celigo
Bearer authentication, not the JSON-RPC MCP proxy used by the catalog and
policy mixins.
"""

from __future__ import annotations

__author__ = "Idea Bosque"

from typing import Any, Dict

import humps

from .celigo_backed_processor import CeligoBackedProcessor
from .error_handler import (
    ErrorCode,
    handle_errors,
    is_empty_result,
    propagate_error_if_present,
    validate_not_empty,
    ValidationError,
)


class OrderMixin(CeligoBackedProcessor):

    @handle_errors(operation_name="lookup_order")
    def lookup_order(self, **arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Look up orders via the Celigo integrator.io orders REST endpoint.

        The caller's non-empty arguments are forwarded verbatim as the JSON
        POST request body (e.g. ``order_id`` or the filter fields the target
        lookup integration expects); when nothing is supplied the request is
        sent without a body, mirroring the reference curl:

            curl -X POST "https://api.integrator.io/apis/v1/api/orders" \\
                -H "Authorization: Bearer <celigo token>"

        Endpoint URL, bearer token, timeout, and retry behavior come from the
        ``celigo_mcp`` settings (``orders_endpoint``, ``bearer_token``).
        Response data is normalized to snake_case, like every other tool; an
        empty response becomes a friendly no-results string.
        """
        body = {
            key: value
            for key, value in arguments.items()
            if value is not None and value != ""
        }

        result = self._execute_order_lookup(body if body else None)
        if error := propagate_error_if_present(result):
            return error

        data = humps.decamelize(result) if isinstance(result, (dict, list)) else result

        if is_empty_result(data):
            return "No orders found for the provided lookup criteria."

        return data

    # snake_case MCP argument -> camelCase REST body field
    _RETURN_FIELD_MAP = {
        "order_id": "orderId",
        "quantity": "quantity",
        "fulfillment_line_item_id": "fulfillmentLineItemId",
    }

    @handle_errors(operation_name="create_return")
    def create_return(self, **arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create an order return via the Celigo integrator.io REST endpoint.

        POSTs ``https://api.integrator.io/apis/v1/api/return`` with the
        Celigo bearer token and a JSON body built from the MCP arguments::

            {"orderId": "gid://shopify/Order/...", "quantity": 10,
             "fulfillmentLineItemId": "gid://shopify/FulfillmentLineItem/..."}

        snake_case arguments are mapped to the API's camelCase fields
        (``order_id`` -> ``orderId``, ``fulfillment_line_item_id`` ->
        ``fulfillmentLineItemId``); unknown fields are forwarded verbatim
        (they are expected to already be camelCase). ``order_id`` and
        ``fulfillment_line_item_id`` are required; ``quantity`` must be a
        positive integer. This is a mutation — no automatic retries, so
        callers should retry deliberately.
        """
        body: Dict[str, Any] = {}
        for key, value in arguments.items():
            if value is None or value == "":
                continue
            body[self._RETURN_FIELD_MAP.get(key, key)] = value

        for field in ("orderId", "fulfillmentLineItemId"):
            validate_not_empty(body.get(field), field)

        try:
            quantity = int(body.get("quantity"))
        except (TypeError, ValueError):
            quantity = None
        if quantity is None or quantity <= 0:
            raise ValidationError(
                message="quantity must be a positive integer",
                error_code=ErrorCode.VALIDATION_FAILED,
                details={"field": "quantity"},
            )
        body["quantity"] = quantity

        result = self._execute_return_creation(body)
        if error := propagate_error_if_present(result):
            return error

        data = humps.decamelize(result) if isinstance(result, (dict, list)) else result

        if is_empty_result(data):
            return (
                "Return request submitted for order %s (%s x%s)."
                % (
                    body.get("orderId"),
                    body.get("fulfillmentLineItemId"),
                    body.get("quantity"),
                )
            )

        return data