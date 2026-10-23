#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP Configuration for Celigo Shopify Bridge"""

__author__ = "bibow"

# MCP Configuration
MCP_CONFIGURATION = {
    "tools": [
        # Catalog Tools (3)
        {
            "name": "search_catalog",
            "description": "Search the storefront product catalog with a natural language query. Returns products with title, description, price range, availability, variants, options, media, and pagination. Follows the Shopify UCP catalog search convention.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query, e.g. 'snowboard', 'organic coffee beans', 'winter jacket'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of products to return (default 10, max 250)",
                    },
                    "cursor": {
                        "type": "string",
                        "description": "Opaque pagination cursor from a previous response",
                    },
                    "context": {
                        "type": "object",
                        "description": "Buyer context signals for relevance and localization (e.g. address_country, language, currency, intent)",
                    },
                    "pagination": {
                        "type": "object",
                        "description": "Cursor-based pagination controls (object with cursor and limit)",
                    },
                    "meta": {
                        "type": "object",
                        "description": "UCP agent metadata passed through verbatim (e.g. ucp-agent profile); auto-injected when omitted",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_product",
            "description": "Retrieve complete product detail by identifier (product or variant GID, e.g. gid://shopify/Product/8184009359547). Returns the full UCP product envelope: title, description, price range, variants with availability and media, options with availability signals, and checkout URLs. Supports interactive variant narrowing via 'selected' option selections and 'preferences' relaxation order.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Product or variant identifier, e.g. 'gid://shopify/Product/8184009359547'",
                    },
                    "selected": {
                        "type": "array",
                        "description": "Partial or full option selections for interactive variant narrowing, e.g. [{\"name\": \"Color\", \"label\": \"Hydrogen\"}]; response option values include availability signals relative to these selections",
                    },
                    "preferences": {
                        "type": "array",
                        "description": "Option names in relaxation priority order, e.g. ['Color', 'Size'] — when no exact variant matches all selections, options are dropped from the end of this list first",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Filter criteria to narrow returned variants (AND logic)",
                    },
                    "context": {
                        "type": "object",
                        "description": "Buyer context signals for relevance and localization (e.g. address_country, language, currency)",
                    },
                    "signals": {
                        "type": "object",
                        "description": "UCP signals object passed through verbatim",
                    },
                    "attribution": {
                        "type": "object",
                        "description": "UCP attribution object passed through verbatim",
                    },
                    "meta": {
                        "type": "object",
                        "description": "UCP agent metadata passed through verbatim (e.g. ucp-agent profile); auto-injected when omitted",
                    },
                },
                "required": ["id"],
            },
        },
        {
            "name": "lookup_catalog",
            "description": "Batch lookup of products or variants by identifier (UCP catalog lookup). Returns matching products with variant correlation metadata. Note: the Celigo UCP proxy currently rejects well-formed requests for this tool ('missing required properties: ids'); prefer get_product for single-product retrieval.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "description": "Identifiers to lookup (product IDs and variant IDs MUST be supported; SKU/handle support is merchant-dependent), e.g. ['gid://shopify/Product/8184009359547']",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Filter criteria to narrow returned products and variants (AND logic)",
                    },
                    "context": {
                        "type": "object",
                        "description": "Buyer context signals for relevance and localization",
                    },
                    "signals": {
                        "type": "object",
                        "description": "UCP signals object passed through verbatim",
                    },
                    "attribution": {
                        "type": "object",
                        "description": "UCP attribution object passed through verbatim",
                    },
                    "meta": {
                        "type": "object",
                        "description": "UCP agent metadata passed through verbatim (e.g. ucp-agent profile); auto-injected when omitted",
                    },
                },
                "required": ["ids"],
            },
        },
        # Policy & FAQ Tools (1)
        {
            "name": "search_shop_policies_and_faqs",
            "description": "Search shop policies and FAQs by natural language query. Returns matching question and answer records covering topics such as shipping, returns, refunds, privacy, and payment. Routed through the legacy Celigo MCP endpoint (the UCP route requires buyer JWT authentication).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query, e.g. 'what is your shipping policy'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of records to return (optional)",
                    },
                },
                "required": ["query"],
            },
        },
        # Order Tools (1)
        {
            "name": "lookup_order",
            "description": "Look up orders via the Celigo integrator.io order lookup REST API (POST https://api.integrator.io/apis/v1/api/orders). Provided fields are sent verbatim as the JSON request body — include 'order_id' or the filter fields the target lookup integration expects; with no fields the request is sent without a body. LIVE: the endpoint currently ignores body filters and returns the shop's recent orders with pagination. Uses the configured Celigo bearer token for authentication.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order identifier to look up, e.g. 'gid://shopify/Order/123' or the internal order id expected by the lookup integration",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Additional lookup/filter criteria forwarded verbatim in the request body (AND logic)",
                    },
                },
                "required": [],
            },
        },
        # Generic Celigo Tool Invocation (escape hatch)
        {
            "name": "call_celigo_tool",
            "description": "Invoke any other Celigo integrator.io MCP tool by name. Use only for tools not covered by dedicated tools (e.g. cart, checkout, and order operations such as create_cart, get_cart, create_checkout, get_order — these require Shopify buyer JWT authentication via arguments.meta): the tool name is a variable passed in 'name' together with its 'arguments' object.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Celigo MCP tool name to invoke, e.g. 'search_shop_policies_and_faqs'",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Tool arguments object, e.g. {\"query\": \"what is your shipping policy\"}",
                    },
                },
                "required": ["name"],
            },
        },
    ],
    "module_links": [
        # Catalog Tools
        {
            "type": "tool",
            "name": "search_catalog",
            "module_name": "mcp_celigo_shopify_bridge",
            "class_name": "MCPCeligoBridge",
            "function_name": "search_catalog",
            "return_type": "text",
        },
        {
            "type": "tool",
            "name": "get_product",
            "module_name": "mcp_celigo_shopify_bridge",
            "class_name": "MCPCeligoBridge",
            "function_name": "get_product",
            "return_type": "text",
        },
        {
            "type": "tool",
            "name": "lookup_catalog",
            "module_name": "mcp_celigo_shopify_bridge",
            "class_name": "MCPCeligoBridge",
            "function_name": "lookup_catalog",
            "return_type": "text",
        },
        # Policy & FAQ Tools
        {
            "type": "tool",
            "name": "search_shop_policies_and_faqs",
            "module_name": "mcp_celigo_shopify_bridge",
            "class_name": "MCPCeligoBridge",
            "function_name": "search_shop_policies_and_faqs",
            "return_type": "text",
        },
        # Order Tools
        {
            "type": "tool",
            "name": "lookup_order",
            "module_name": "mcp_celigo_shopify_bridge",
            "class_name": "MCPCeligoBridge",
            "function_name": "lookup_order",
            "return_type": "text",
        },
        # Generic Celigo Tool Invocation (escape hatch)
        {
            "type": "tool",
            "name": "call_celigo_tool",
            "module_name": "mcp_celigo_shopify_bridge",
            "class_name": "MCPCeligoBridge",
            "function_name": "call_celigo_tool",
            "return_type": "text",
        },
    ],
    "modules": [
        {
            "package_name": "mcp_celigo_shopify_bridge",
            "module_name": "mcp_celigo_shopify_bridge",
            "class_name": "MCPCeligoBridge",
            # Default settings consumed by MCPCeligoBridge / CeligoClient.
            # Override per-deployment (e.g. via environment-specific config).
            "setting": {
                # Celigo MCP backend module. Both routes speak JSON-RPC 2.0
                # (tools/call) over HTTP POST and authenticate with a Celigo
                # Bearer token. The primary endpoint proxies the Shopify UCP
                # catalog tools; legacy-routed tools (see legacy_tools) go to
                # the legacy endpoint.
                "celigo_mcp": {
                    "endpoint": "https://api.integrator.io/apis/v1/api/ucp/mcp",
                    "legacy_endpoint": "https://api.integrator.io/apis/v1/api/mcp",
                    "legacy_tools": ["search_shop_policies_and_faqs"],
                    "orders_endpoint": "https://api.integrator.io/apis/v1/api/orders",
                    "bearer_token": "89f3690302b34641999a7f40d984f76a",
                    "timeout": 60,
                    "connect_timeout": 15,
                    "max_retries": 1,
                },
            },
        }
    ],
}