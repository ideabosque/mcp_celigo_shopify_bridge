#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for MCP Celigo Bridge â€” tool registration, argument mapping,
response normalization, and error propagation (mocked Celigo execution)."""
from __future__ import annotations

__author__ = "Idea Bosque"

import json
from unittest.mock import MagicMock

import pytest

from mcp_celigo_shopify_bridge import MCP_CONFIGURATION
from mcp_celigo_shopify_bridge.celigo_client import CeligoClient
from mcp_celigo_shopify_bridge.error_handler import (
    ErrorCode,
    CeligoError,
    build_error_response,
    is_empty_result,
    validate_not_empty,
)


# ==================== Tool Registration ====================


class TestToolRegistration:
    def test_configuration_has_tools(self):
        assert len(MCP_CONFIGURATION["tools"]) == 6

    def test_configuration_has_module_links(self):
        links = MCP_CONFIGURATION["module_links"]
        assert len(links) == 6
        by_name = {link["name"]: link for link in links}
        for name in (
            "search_catalog",
            "get_product",
            "lookup_catalog",
            "search_shop_policies_and_faqs",
            "lookup_order",
            "call_celigo_tool",
        ):
            link = by_name[name]
            assert link["module_name"] == "mcp_celigo_shopify_bridge"
            assert link["class_name"] == "MCPCeligoBridge"
            assert link["function_name"] == name
            assert link["return_type"] == "text"

    def test_configuration_module_entry(self):
        modules = MCP_CONFIGURATION["modules"]
        assert len(modules) == 1
        module = modules[0]
        assert module["package_name"] == "mcp_celigo_shopify_bridge"
        assert module["class_name"] == "MCPCeligoBridge"
        assert "celigo_mcp" in module["setting"]

    def test_every_tool_has_schema_and_link(self):
        tool_names = {t["name"] for t in MCP_CONFIGURATION["tools"]}
        link_names = {l["name"] for l in MCP_CONFIGURATION["module_links"]}
        assert tool_names == link_names
        for tool in MCP_CONFIGURATION["tools"]:
            schema = tool["inputSchema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema

    def test_facade_exposes_all_tools(self, processor):
        for link in MCP_CONFIGURATION["module_links"]:
            assert callable(getattr(processor, link["function_name"]))

    def test_name_is_a_variable_in_schema(self):
        tool = {t["name"]: t for t in MCP_CONFIGURATION["tools"]}["call_celigo_tool"]
        properties = tool["inputSchema"]["properties"]
        assert "name" in properties
        assert properties["name"]["type"] == "string"
        assert "arguments" in properties
        assert properties["arguments"]["type"] == "object"


# ==================== search_catalog ====================


class TestSearchCatalog:
    def test_requires_query(self, processor):
        result = processor.search_catalog()
        assert "error" in result
        assert "query" in result["error"]

    def test_builds_catalog_envelope(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {
                "ucp": {"version": "2026-08-25"},
                "products": [{"title": "The Collection Snowboard: Hydrogen",
                              "price_range": {"min": {"amount": 60000},
                                              "max": {"amount": 60000}}}],
                "pagination": {"has_next_page": False},
            }
        )
        result = processor.search_catalog(query="snowboard")
        processor._execute_celigo_call.assert_called_once_with(
            "search_catalog",
            {"catalog": {"query": "snowboard"}},
        )
        assert result["products"][0]["title"] == "The Collection Snowboard: Hydrogen"

    def test_flat_limit_and_cursor_become_pagination(
        self, processor, celigo_result_factory
    ):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"products": [{"title": "P"}]}
        )
        processor.search_catalog(query="snowboard", limit=5, cursor="abc")
        processor._execute_celigo_call.assert_called_once_with(
            "search_catalog",
            {"catalog": {
                "query": "snowboard",
                "pagination": {"limit": 5, "cursor": "abc"},
            }},
        )

    def test_explicit_pagination_object_wins(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"products": [{"title": "P"}]}
        )
        processor.search_catalog(
            query="snowboard", pagination={"limit": 20}, limit=5
        )
        processor._execute_celigo_call.assert_called_once_with(
            "search_catalog",
            {"catalog": {
                "query": "snowboard",
                "pagination": {"limit": 20},
            }},
        )

    def test_context_and_meta_passed_through(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"products": [{"title": "P"}]}
        )
        processor.search_catalog(
            query="snowboard",
            context={"address_country": "US"},
            meta={"ucp-agent": {"profile": "https://example.test/profile"}},
        )
        call_args = processor._execute_celigo_call.call_args
        tool_arguments = call_args[0][1]
        assert tool_arguments["catalog"]["context"] == {"address_country": "US"}
        assert tool_arguments["meta"]["ucp-agent"]["profile"] == (
            "https://example.test/profile"
        )

    def test_empty_products_returns_friendly_message(
        self, processor, celigo_result_factory
    ):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"products": [], "pagination": {"has_next_page": False}}
        )
        result = processor.search_catalog(query="obscure item")
        assert result == "No catalog results found for this query."

    def test_propagates_client_error(self, processor):
        processor._execute_celigo_call.return_value = build_error_response(
            message="Celigo API returned HTTP 503",
            error_code=ErrorCode.CELIGO_API_ERROR,
        )
        result = processor.search_catalog(query="snowboard")
        assert result["error_code"] == ErrorCode.CELIGO_API_ERROR


# ==================== get_product ====================


class TestGetProduct:
    def test_requires_id(self, processor):
        result = processor.get_product()
        assert "error" in result
        assert "id" in result["error"]

    def test_rejects_empty_id(self, processor):
        result = processor.get_product(id="   ")
        assert "error" in result

    def test_builds_catalog_envelope(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {
                "ucp": {"version": "2026-08-25", "status": "success"},
                "product": {"id": "gid://shopify/Product/8184009359547",
                            "title": "The Collection Snowboard: Hydrogen"},
                "messages": [],
            }
        )
        result = processor.get_product(id="gid://shopify/Product/8184009359547")
        processor._execute_celigo_call.assert_called_once_with(
            "get_product",
            {"catalog": {"id": "gid://shopify/Product/8184009359547"}},
        )
        assert result["product"]["title"] == "The Collection Snowboard: Hydrogen"

    def test_accepts_product_id_alias(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"product": {"id": "gid://shopify/Product/1"}}
        )
        processor.get_product(product_id="gid://shopify/Product/1")
        processor._execute_celigo_call.assert_called_once_with(
            "get_product",
            {"catalog": {"id": "gid://shopify/Product/1"}},
        )

    def test_selected_and_preferences_passed_through(
        self, processor, celigo_result_factory
    ):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"product": {"id": "gid://shopify/Product/1"}}
        )
        processor.get_product(
            id="gid://shopify/Product/1",
            selected=[{"name": "Color", "label": "Hydrogen"}],
            preferences=["Color", "Size"],
        )
        call_args = processor._execute_celigo_call.call_args
        catalog = call_args[0][1]["catalog"]
        assert catalog["selected"] == [{"name": "Color", "label": "Hydrogen"}]
        assert catalog["preferences"] == ["Color", "Size"]

    def test_meta_passed_through(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"product": {"id": "gid://shopify/Product/1"}}
        )
        meta = {"ucp-agent": {"profile": "https://example.test/profile"}}
        processor.get_product(id="gid://shopify/Product/1", meta=meta)
        call_args = processor._execute_celigo_call.call_args
        assert call_args[0][1]["meta"] == meta

    def test_missing_product_returns_friendly_message(
        self, processor, celigo_result_factory
    ):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"ucp": {"version": "2026-08-25"}, "product": None, "messages": []}
        )
        result = processor.get_product(id="gid://shopify/Product/999")
        assert result == "No product found for id 'gid://shopify/Product/999'."

    def test_propagates_client_error(self, processor):
        processor._execute_celigo_call.return_value = build_error_response(
            message="Celigo API returned HTTP 503",
            error_code=ErrorCode.CELIGO_API_ERROR,
        )
        result = processor.get_product(id="gid://shopify/Product/1")
        assert result["error_code"] == ErrorCode.CELIGO_API_ERROR

    def test_exception_returns_error_dict(self, processor):
        processor._execute_celigo_call.side_effect = RuntimeError("boom")
        result = processor.get_product(id="gid://shopify/Product/1")
        assert "error" in result
        assert result["error_code"] == ErrorCode.UNKNOWN_ERROR

    def test_product_not_found_returns_friendly_message(self, processor):
        from mcp_celigo_shopify_bridge.celigo_client import CeligoError

        processor._execute_celigo_call.side_effect = CeligoError(
            message="product_not_found: Product not found",
            error_code=ErrorCode.CELIGO_API_ERROR,
            details={"code": "product_not_found", "severity": "unrecoverable", "source": "ucp_messages"},
        )
        result = processor.get_product(id="gid://shopify/Product/1")
        assert result == "No product found for id 'gid://shopify/Product/1'."


# ==================== lookup_catalog ====================


class TestLookupCatalog:
    def test_requires_ids(self, processor):
        result = processor.lookup_catalog()
        assert "error" in result
        assert "ids" in result["error"]

    def test_rejects_empty_ids_list(self, processor):
        result = processor.lookup_catalog(ids=[])
        assert "error" in result

    def test_rejects_non_list_ids(self, processor):
        result = processor.lookup_catalog(ids=12345)
        assert "error" in result

    def test_builds_catalog_envelope(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {
                "products": [{"id": "gid://shopify/Product/8184009359547",
                              "title": "The Collection Snowboard: Hydrogen"}],
            }
        )
        result = processor.lookup_catalog(
            ids=["gid://shopify/Product/8184009359547"]
        )
        processor._execute_celigo_call.assert_called_once_with(
            "lookup_catalog",
            {"catalog": {"ids": ["gid://shopify/Product/8184009359547"]}},
        )
        assert result["products"][0]["title"] == (
            "The Collection Snowboard: Hydrogen"
        )

    def test_single_id_string_becomes_list(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"products": [{"id": "gid://shopify/Product/1"}]}
        )
        processor.lookup_catalog(ids="gid://shopify/Product/1")
        processor._execute_celigo_call.assert_called_once_with(
            "lookup_catalog",
            {"catalog": {"ids": ["gid://shopify/Product/1"]}},
        )

    def test_filters_passed_through(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"products": [{"id": "gid://shopify/Product/1"}]}
        )
        processor.lookup_catalog(
            ids=["gid://shopify/Product/1"],
            filters={"availability": "in_stock"},
        )
        call_args = processor._execute_celigo_call.call_args
        assert call_args[0][1]["catalog"]["filters"] == {
            "availability": "in_stock"
        }

    def test_empty_products_returns_friendly_message(
        self, processor, celigo_result_factory
    ):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"products": []}
        )
        result = processor.lookup_catalog(ids=["gid://shopify/Product/999"])
        assert result == "No catalog results found for the requested identifiers."

    def test_propagates_client_error(self, processor):
        processor._execute_celigo_call.return_value = build_error_response(
            message="Celigo API returned HTTP 503",
            error_code=ErrorCode.CELIGO_API_ERROR,
        )
        result = processor.lookup_catalog(ids=["gid://shopify/Product/1"])
        assert result["error_code"] == ErrorCode.CELIGO_API_ERROR


# ==================== search_shop_policies_and_faqs ====================


class TestSearchShopPoliciesAndFaqs:
    def test_requires_query(self, processor):
        result = processor.search_shop_policies_and_faqs()
        assert "error" in result
        assert "query" in result["error"]

    def test_rejects_empty_query(self, processor):
        result = processor.search_shop_policies_and_faqs(query="   ")
        assert "error" in result

    def test_builds_tool_call_with_query(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            [{"question": "What countries do you ship to?",
              "answer": "US, CA, GB, AU"}]
        )
        result = processor.search_shop_policies_and_faqs(
            query="what is your shipping policy"
        )
        processor._execute_celigo_call.assert_called_once_with(
            "search_shop_policies_and_faqs",
            {"query": "what is your shipping policy"},
        )
        assert isinstance(result, list)
        assert result[0]["question"] == "What countries do you ship to?"

    def test_passes_limit_when_provided(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory([])
        processor.search_shop_policies_and_faqs(query="shipping", limit=5)
        processor._execute_celigo_call.assert_called_once_with(
            "search_shop_policies_and_faqs",
            {"query": "shipping", "limit": 5},
        )

    def test_empty_result_returns_friendly_message(
        self, processor, celigo_result_factory
    ):
        processor._execute_celigo_call.return_value = celigo_result_factory([])
        result = processor.search_shop_policies_and_faqs(query="obscure topic")
        assert result == "No shop policies or FAQs found for this query."

    def test_propagates_client_error(self, processor):
        processor._execute_celigo_call.return_value = build_error_response(
            message="Celigo API returned HTTP 503",
            error_code=ErrorCode.CELIGO_API_ERROR,
        )
        result = processor.search_shop_policies_and_faqs(query="shipping")
        assert result["error_code"] == ErrorCode.CELIGO_API_ERROR

    def test_exception_returns_error_dict(self, processor):
        processor._execute_celigo_call.side_effect = RuntimeError("boom")
        result = processor.search_shop_policies_and_faqs(query="shipping")
        assert "error" in result
        assert result["error_code"] == ErrorCode.UNKNOWN_ERROR


# ==================== lookup_order ====================


class TestLookupOrder:
    def test_forwards_body_verbatim(self, processor, celigo_result_factory):
        processor._execute_order_lookup.return_value = celigo_result_factory(
            {"orderId": "123", "total": "59.99"}
        )
        result = processor.lookup_order(order_id="gid://shopify/Order/123")
        processor._execute_order_lookup.assert_called_once_with(
            {"order_id": "gid://shopify/Order/123"}
        )
        assert result == {"order_id": "123", "total": "59.99"}

    def test_no_arguments_sends_no_body(self, processor, celigo_result_factory):
        processor._execute_order_lookup.return_value = celigo_result_factory(
            [{"orderId": "123"}]
        )
        result = processor.lookup_order()
        processor._execute_order_lookup.assert_called_once_with(None)
        assert result == [{"order_id": "123"}]

    def test_filters_forwarded_in_body(self, processor, celigo_result_factory):
        processor._execute_order_lookup.return_value = celigo_result_factory(
            {"orderList": []}
        )
        processor.lookup_order(filters={"status": "paid"})
        processor._execute_order_lookup.assert_called_once_with(
            {"filters": {"status": "paid"}}
        )

    def test_empty_result_returns_friendly_message(
        self, processor, celigo_result_factory
    ):
        processor._execute_order_lookup.return_value = celigo_result_factory([])
        result = processor.lookup_order(order_id="999")
        assert result == "No orders found for the provided lookup criteria."

    def test_propagates_client_error(self, processor):
        processor._execute_order_lookup.return_value = build_error_response(
            message="Celigo API returned HTTP 401: unauthorized",
            error_code=ErrorCode.CELIGO_API_ERROR,
        )
        result = processor.lookup_order(order_id="1")
        assert result["error_code"] == ErrorCode.CELIGO_API_ERROR

    def test_exception_returns_error_dict(self, processor):
        processor._execute_order_lookup.side_effect = RuntimeError("boom")
        result = processor.lookup_order(order_id="1")
        assert "error" in result
        assert result["error_code"] == ErrorCode.UNKNOWN_ERROR


# ==================== call_celigo_tool ====================


class TestCallCeligoTool:
    def test_requires_name(self, processor):
        result = processor.call_celigo_tool()
        assert "error" in result
        assert "name" in result["error"]

    def test_rejects_non_dict_arguments(self, processor):
        result = processor.call_celigo_tool(
            name="search_shop_policies_and_faqs", arguments="query"
        )
        assert "error" in result
        assert result["error_code"] == ErrorCode.INVALID_ARGUMENTS

    def test_forwards_name_and_arguments(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            [{"question": "What countries do you ship to?",
              "answer": "US, CA, GB, AU"}]
        )
        result = processor.call_celigo_tool(
            name="search_shop_policies_and_faqs",
            arguments={"query": "what is your shipping policy"},
        )
        processor._execute_celigo_call.assert_called_once_with(
            "search_shop_policies_and_faqs",
            {"query": "what is your shipping policy"},
        )
        assert isinstance(result, list)
        assert result[0]["question"] == "What countries do you ship to?"

    def test_name_without_arguments(self, processor, celigo_result_factory):
        processor._execute_celigo_call.return_value = celigo_result_factory(
            {"status": "ok"}
        )
        processor.call_celigo_tool(name="get_shop")
        processor._execute_celigo_call.assert_called_once_with(
            "get_shop", {}
        )

    def test_empty_result_returns_friendly_message(
        self, processor, celigo_result_factory
    ):
        processor._execute_celigo_call.return_value = celigo_result_factory([])
        result = processor.call_celigo_tool(
            name="search_shop_policies_and_faqs", arguments={"query": "x"}
        )
        assert result == (
            "No results returned by Celigo tool 'search_shop_policies_and_faqs'."
        )

    def test_propagates_client_error(self, processor):
        processor._execute_celigo_call.return_value = build_error_response(
            message="Celigo API returned HTTP 503",
            error_code=ErrorCode.CELIGO_API_ERROR,
        )
        result = processor.call_celigo_tool(name="get_shop")
        assert result["error_code"] == ErrorCode.CELIGO_API_ERROR

    def test_exception_returns_error_dict(self, processor):
        processor._execute_celigo_call.side_effect = RuntimeError("boom")
        result = processor.call_celigo_tool(name="get_shop")
        assert "error" in result
        assert result["error_code"] == ErrorCode.UNKNOWN_ERROR


# ==================== CeligoClient response handling ====================


class TestCeligoClientResponseHandling:
    def _client(self):
        client = CeligoClient.__new__(CeligoClient)
        client.logger = MagicMock()
        client.setting = {}
        client.endpoint_id = None
        client.part_id = None
        return client

    @staticmethod
    def _response(body: dict):
        response = MagicMock()
        response.status_code = 200
        response.content = b"non-empty"
        response.json.return_value = body
        return response

    def test_parses_stringified_list_result(self):
        client = self._client()
        response = self._response(
            {"result": json.dumps(
                [{"question": "Q1", "answer": "A1"}]
            )}
        )
        assert client._handle_response(response) == [
            {"question": "Q1", "answer": "A1"}
        ]

    def test_parses_stringified_dict_result(self):
        client = self._client()
        response = self._response(
            {"result": json.dumps({"faqList": [{"question": "Q1"}]})}
        )
        assert client._handle_response(response) == {
            "faq_list": [{"question": "Q1"}]
        }

    def test_parses_ucp_envelope_success(self):
        client = self._client()
        response = self._response(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {"name": "get_product", "arguments": {}},
                "text": [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(
                                        {
                                            "ucp": {"version": "2026-08-25"},
                                            "product": {
                                                "id": "gid://shopify/Product/1",
                                                "title": "Snowboard",
                                            },
                                        }
                                    ),
                                }
                            ]
                        },
                    }
                ],
            }
        )
        data = client._handle_response(response)
        assert data["product"]["title"] == "Snowboard"
        assert data["ucp"]["version"] == "2026-08-25"

    def test_ucp_envelope_is_error_raises(self):
        client = self._client()
        response = self._response(
            {
                "text": [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "content": [
                                {"type": "text", "text": "Missing required arguments: id"}
                            ],
                            "isError": True,
                        },
                    }
                ]
            }
        )
        with pytest.raises(CeligoError):
            client._handle_response(response)

    def test_ucp_envelope_is_error_condenses_messages(self):
        client = self._client()
        ucp_error = json.dumps(
            {
                "ucp": {"version": "2026-08-25", "status": "error"},
                "messages": [
                    {
                        "type": "error",
                        "content_type": "plain",
                        "code": "product_not_found",
                        "content": "Product not found",
                        "severity": "unrecoverable",
                    }
                ],
            }
        )
        response = self._response(
            {
                "text": [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "content": [{"type": "text", "text": ucp_error}],
                            "isError": True,
                        },
                    }
                ]
            }
        )
        with pytest.raises(CeligoError) as excinfo:
            client._handle_response(response)
        assert excinfo.value.message == "product_not_found: Product not found"
        assert excinfo.value.details.get("code") == "product_not_found"
        assert excinfo.value.details.get("severity") == "unrecoverable"
        assert excinfo.value.details.get("source") == "ucp_messages"

    def test_ucp_envelope_errors_array_raises_with_details(self):
        client = self._client()
        inner_error = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {
                    "code": -32000,
                    "message": "AuthenticationRequired",
                    "data": "Unauthorized: A valid JWT is required to call get_order.",
                },
            }
        )
        response = self._response(
            {
                "errors": [
                    {"code": 403, "source": "application", "message": inner_error}
                ]
            }
        )
        with pytest.raises(CeligoError) as excinfo:
            client._handle_response(response)
        assert "AuthenticationRequired" in excinfo.value.message
        assert "A valid JWT" in excinfo.value.message
        assert excinfo.value.details.get("code") == -32000

    def test_ucp_envelope_rpc_error_raises(self):
        client = self._client()
        response = self._response(
            {
                "text": [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "error": {"code": -32602, "message": "Invalid params",
                                  "data": "Tool not found: bogus"},
                    }
                ]
            }
        )
        with pytest.raises(CeligoError):
            client._handle_response(response)

    def test_ucp_envelope_without_result_raises(self):
        client = self._client()
        response = self._response({"text": []})
        with pytest.raises(CeligoError):
            client._handle_response(response)

    def test_non_json_result_string_raises(self):
        client = self._client()
        response = self._response(
            {"result": '3:query is required. debug_error_string:{...}'}
        )
        with pytest.raises(CeligoError):
            client._handle_response(response)

    def test_strips_shopify_deprecation_notice(self):
        client = self._client()
        payload = (
            '{"ucp":{"version":"2026-08-25"},"products":[{"title":"Snowboard"}],'
            '"pagination":{"has_next_page":false}},'
            "DEPRECATION NOTICE: This tool is served by the Storefront MCP "
            "server at /api/mcp and will no longer be accessible after "
            "August 31, 2026. Migrate to the UCP-conforming tools at "
            "/api/ucp/mcp. See https://shopify.dev/docs/agents for "
            "migration details."
        )
        response = self._response({"result": payload})
        data = client._handle_response(response)
        assert data["products"][0]["title"] == "Snowboard"
        assert "deprecation" not in json.dumps(data).lower()

    def test_empty_body_returns_empty_list(self):
        client = self._client()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = None
        response.content = b""
        assert client._handle_response(response) == []

    def test_jsonrpc_error_envelope_raises(self):
        client = self._client()
        response = self._response(
            {"error": {"code": -32602, "message": "Invalid params"}}
        )
        with pytest.raises(CeligoError):
            client._handle_response(response)

    def test_http_error_raises(self):
        client = self._client()
        response = MagicMock()
        response.status_code = 401
        response.text = "unauthorized"
        with pytest.raises(CeligoError):
            client._handle_response(response)

    def test_normalizes_camel_case_keys(self):
        client = self._client()
        assert client._normalize({"faqList": [{"questionText": "Q"}]}) == {
            "faq_list": [{"question_text": "Q"}]
        }


# ==================== CeligoClient routing & meta injection ====================


class TestCeligoClientRouting:
    """Endpoint routing and UCP meta injection (mocked HTTP, never sent)."""

    def _live_client(self, **overrides):
        setting = {
            "celigo_mcp": {
                "endpoint": "https://ucp.example.test/mcp",
                "legacy_endpoint": "https://legacy.example.test/mcp",
                "bearer_token": "tok",
                "max_retries": 0,
                **overrides,
            }
        }
        client = CeligoClient(MagicMock(), **setting)
        client._http_client = MagicMock()
        # Well-behaved mock response so call_tool completes cleanly.
        response = MagicMock()
        response.status_code = 200
        response.content = b"{}"
        response.json.return_value = {"result": "{\"ok\": true}"}
        client._http_client.post.return_value = response
        return client

    def test_legacy_tools_route_to_legacy_endpoint(self):
        client = self._live_client()
        client.call_tool(
            "search_shop_policies_and_faqs", {"query": "shipping"}
        )
        url = client._http_client.post.call_args[0][0]
        assert url == "https://legacy.example.test/mcp"

    def test_ucp_tools_route_to_primary_endpoint(self):
        client = self._live_client()
        client.call_tool(
            "get_product", {"catalog": {"id": "gid://shopify/Product/1"}}
        )
        url = client._http_client.post.call_args[0][0]
        assert url == "https://ucp.example.test/mcp"

    def test_ucp_meta_auto_injected_when_missing(self):
        client = self._live_client()
        client.call_tool(
            "get_product", {"catalog": {"id": "gid://shopify/Product/1"}}
        )
        payload = client._http_client.post.call_args[1]["json"]
        meta = payload["params"]["arguments"]["meta"]
        assert meta["ucp-agent"]["profile"].startswith("https://shopify.dev/ucp/")

    def test_caller_meta_profile_not_clobbered(self):
        client = self._live_client()
        meta = {"ucp-agent": {"profile": "https://example.test/profile"}}
        client.call_tool("get_product", {"meta": meta, "catalog": {"id": "x"}})
        payload = client._http_client.post.call_args[1]["json"]
        assert payload["params"]["arguments"]["meta"] == meta

    def test_custom_ucp_profile_setting(self):
        client = self._live_client(
            ucp_agent_profile="https://custom.test/profile.json"
        )
        injected = client._with_ucp_meta({})
        assert (
            injected["meta"]["ucp-agent"]["profile"]
            == "https://custom.test/profile.json"
        )

    def test_default_endpoints_are_ucp_and_legacy(self):
        client = CeligoClient(MagicMock())
        assert client._endpoint == "https://api.integrator.io/apis/v1/api/ucp/mcp"
        assert (
            client._legacy_endpoint == "https://api.integrator.io/apis/v1/api/mcp"
        )
        assert "search_shop_policies_and_faqs" in client._legacy_tools
        assert (
            client._orders_endpoint
            == "https://api.integrator.io/apis/v1/api/orders"
        )

    def test_order_lookup_posts_to_orders_endpoint(self):
        client = CeligoClient(
            MagicMock(),
            **{
                "celigo_mcp": {
                    "bearer_token": "tok",
                    "max_retries": 0,
                }
            },
        )
        client._http_client = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"result": {"ok": true}}'
        response.json.return_value = {"result": {"ok": True}}
        client._http_client.post.return_value = response

        data = client.lookup_orders({"id": "1"})

        client._http_client.post.assert_called_once_with(
            "https://api.integrator.io/apis/v1/api/orders",
            json={"id": "1"},
            headers={
                "Authorization": "Bearer tok",
                "Content-Type": "application/json",
            },
        )
        assert data == {"result": {"ok": True}}

    def test_order_lookup_without_payload_sends_no_body(self):
        client = CeligoClient(
            MagicMock(),
            **{
                "celigo_mcp": {
                    "bearer_token": "tok",
                    "max_retries": 0,
                }
            },
        )
        client._http_client = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"result": {"ok": true}}'
        response.json.return_value = {"result": {"ok": True}}
        client._http_client.post.return_value = response

        client.lookup_orders()

        assert client._http_client.post.call_args[1]["json"] is None

    def test_order_lookup_http_error_raises(self):
        client = CeligoClient(
            MagicMock(),
            **{
                "celigo_mcp": {
                    "bearer_token": "tok",
                    "max_retries": 0,
                }
            },
        )
        client._http_client = MagicMock()
        response = MagicMock()
        response.status_code = 401
        response.content = b'{"error": "unauthorized"}'
        client._http_client.post.return_value = response

        with pytest.raises(CeligoError) as excinfo:
            client.lookup_orders({"id": "1"})
        assert excinfo.value.details.get("status_code") == 401

    def test_order_connection_failure_raises_connection_error(self):
        client = CeligoClient(
            MagicMock(),
            **{
                "celigo_mcp": {
                    "bearer_token": "tok",
                    "max_retries": 0,
                }
            },
        )
        client._http_client = MagicMock()
        client._http_client.post.side_effect = RuntimeError("boom")

        with pytest.raises(CeligoError) as excinfo:
            client.lookup_orders({"id": "1"})
        assert excinfo.value.error_code == ErrorCode.API_CONNECTION_FAILED


# ==================== Validation utilities ====================


class TestValidationUtilities:
    def test_validate_not_empty_raises(self):
        with pytest.raises(Exception):
            validate_not_empty(None, "query")

    def test_validate_not_empty_passes(self):
        validate_not_empty("shipping", "query")

    def test_is_empty_result_variants(self):
        assert is_empty_result(None) is True
        assert is_empty_result("") is True
        assert is_empty_result([]) is True
        assert is_empty_result({"total": 0, "faq_list": []}) is True
        assert is_empty_result([{"question": "Q"}]) is False
        assert is_empty_result({"question": "Q"}) is False