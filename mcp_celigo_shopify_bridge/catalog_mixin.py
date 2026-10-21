#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Product catalog mixin for MCP Celigo Shopify Bridge.

Wraps the Shopify UCP catalog tools exposed through the Celigo integrator.io
MCP proxy: ``search_catalog`` (natural-language search), ``get_product``
(single-product detail with optional interactive variant narrowing), and
``lookup_catalog`` (batch lookup by identifier). Typed methods build the
``catalog`` envelope from flat snake_case arguments so MCP hosts never need
to know the UCP shape.
"""

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


class CatalogMixin(CeligoBackedProcessor):

    @handle_errors(operation_name="search_catalog")
    def search_catalog(self, **arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Search the storefront product catalog.

        Accepts ``query`` (required), plus optional ``context`` (UCP buyer
        context object), ``pagination`` (object with ``cursor``/``limit``),
        flat ``limit``/``cursor`` shortcuts, and ``meta`` (UCP agent
        metadata passed through verbatim).
        """
        query = arguments.get("query")
        validate_not_empty(
            query.strip() if isinstance(query, str) else query, "query"
        )
        query = query.strip() if isinstance(query, str) else query

        catalog: Dict[str, Any] = {"query": query}

        context = arguments.get("context")
        if isinstance(context, dict) and context:
            catalog["context"] = context

        pagination = arguments.get("pagination")
        if isinstance(pagination, dict) and pagination:
            catalog["pagination"] = pagination
        else:
            pagination = {}
        limit = arguments.get("limit")
        if limit is not None:
            pagination.setdefault("limit", int(limit))
        cursor = arguments.get("cursor")
        if cursor:
            pagination.setdefault("cursor", cursor)
        if pagination:
            catalog["pagination"] = pagination

        tool_arguments: Dict[str, Any] = {"catalog": catalog}
        meta = arguments.get("meta")
        if isinstance(meta, dict) and meta:
            tool_arguments["meta"] = meta
        tool_arguments = {
            k: v for k, v in tool_arguments.items() if v is not None and v != ""
        }

        tool_name = "search_catalog"
        result = self._execute_celigo_call(tool_name, tool_arguments)
        if error := propagate_error_if_present(result):
            return error

        data = humps.decamelize(result) if isinstance(result, (dict, list)) else result

        # "No result" for catalog search means the products list is empty —
        # the UCP envelope itself is always present.
        products = data.get("products") if isinstance(data, dict) else None
        if is_empty_result(products):
            return "No catalog results found for this query."

        return data

    @handle_errors(operation_name="get_product")
    def get_product(self, **arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve complete product detail by identifier.

        Builds the UCP ``catalog`` request (``catalog_lookup.json``
        ``get_product_request``) from flat snake_case arguments:

        - ``id`` (required): product or variant identifier, e.g.
          ``gid://shopify/Product/8184009359547``
        - ``selected`` (optional): list of ``{"name": ..., "label": ...}``
          option selections for interactive variant narrowing; response
          option values then carry availability signals relative to the
          selection
        - ``preferences`` (optional): list of option names in relaxation
          priority order (dropped from the end first when no exact variant
          matches)
        - ``filters``/``context``/``signals``/``attribution`` (optional):
          UCP objects passed through verbatim
        - ``meta`` (optional): UCP agent metadata (auto-injected by the
          client when omitted)

        The legacy proxy returned empty bodies for this tool; it works on
        the UCP endpoint (verified live).
        """
        product_id = arguments.get("id") or arguments.get("product_id")
        validate_not_empty(
            product_id.strip() if isinstance(product_id, str) else product_id,
            "id",
        )
        product_id = (
            product_id.strip() if isinstance(product_id, str) else product_id
        )

        catalog: Dict[str, Any] = {"id": product_id}
        for key in ("selected", "preferences", "filters", "context", "signals", "attribution"):
            value = arguments.get(key)
            if isinstance(value, (list, dict)) and value:
                catalog[key] = value

        tool_arguments: Dict[str, Any] = {"catalog": catalog}
        meta = arguments.get("meta")
        if isinstance(meta, dict) and meta:
            tool_arguments["meta"] = meta
        tool_arguments = {
            k: v for k, v in tool_arguments.items() if v is not None and v != ""
        }

        tool_name = "get_product"
        result = self._execute_celigo_call(tool_name, tool_arguments)
        if error := propagate_error_if_present(result):
            return error

        data = humps.decamelize(result) if isinstance(result, (dict, list)) else result

        # "No result" for get_product means the product is missing — the UCP
        # envelope itself is always present on success.
        product = data.get("product") if isinstance(data, dict) else None
        if is_empty_result(product):
            return f"No product found for id '{product_id}'."

        return data

    @handle_errors(operation_name="lookup_catalog")
    def lookup_catalog(self, **arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Batch lookup of products or variants by identifier.

        Builds the UCP ``catalog`` request (``catalog_lookup.json``
        ``lookup_request``) from flat snake_case arguments:

        - ``ids`` (required): list of identifiers — product IDs and variant
          IDs MUST be supported; SKU/handle support is merchant-dependent
        - ``filters``/``context``/``signals``/``attribution`` (optional):
          UCP objects passed through verbatim
        - ``meta`` (optional): UCP agent metadata (auto-injected by the
          client when omitted)

        Note: through the Celigo UCP proxy this tool currently rejects
        well-formed ``catalog.ids`` requests ("missing required properties:
        ids"). It is exposed for completeness; use ``get_product`` for
        single-product retrieval or ``call_celigo_tool`` to pass a raw
        argument shape once the proxy accepts one.
        """
        ids = arguments.get("ids")
        if isinstance(ids, str):
            ids = [ids]
        validate_not_empty(ids, "ids")
        if not isinstance(ids, list) or not ids:
            from .error_handler import ErrorCode, ValidationError

            raise ValidationError(
                message="ids must be a non-empty list of identifiers",
                error_code=ErrorCode.INVALID_ARGUMENTS,
                details={"field": "ids"},
            )

        catalog: Dict[str, Any] = {"ids": ids}
        for key in ("filters", "context", "signals", "attribution"):
            value = arguments.get(key)
            if isinstance(value, (list, dict)) and value:
                catalog[key] = value

        tool_arguments: Dict[str, Any] = {"catalog": catalog}
        meta = arguments.get("meta")
        if isinstance(meta, dict) and meta:
            tool_arguments["meta"] = meta
        tool_arguments = {
            k: v for k, v in tool_arguments.items() if v is not None and v != ""
        }

        tool_name = "lookup_catalog"
        result = self._execute_celigo_call(tool_name, tool_arguments)
        if error := propagate_error_if_present(result):
            return error

        data = humps.decamelize(result) if isinstance(result, (dict, list)) else result

        # "No result" for batch lookup means no identifiers resolved.
        products = data.get("products") if isinstance(data, dict) else None
        if is_empty_result(products):
            return "No catalog results found for the requested identifiers."

        return data