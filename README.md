# MCP Celigo Shopify Bridge

`mcp_celigo_shopify_bridge` exposes Celigo integrator.io commerce operations as
SilvaEngine MCP tools backed by the Celigo integrator.io MCP proxy. The proxy
has three routes with different tool surfaces:

- **UCP route** (`https://api.integrator.io/apis/v1/api/ucp/mcp`, primary) —
  proxies the Shopify Storefront MCP's UCP-conforming catalog tools
  (`search_catalog`, `get_product`, `lookup_catalog`).
- **Legacy route** (`https://api.integrator.io/apis/v1/api/mcp`) — proxies the
  legacy Storefront MCP tools; `search_shop_policies_and_faqs` still works here
  (it is buyer-JWT-gated on the UCP route). The legacy catalog tools died with
  the August 31, 2026 Storefront MCP deprecation (HTTP 200 with empty bodies).
- **Order lookup route** (`https://api.integrator.io/apis/v1/api/orders`,
  REST) — plain REST `POST` used by `lookup_order`, not a JSON-RPC MCP
  proxy; consumes the lookup criteria as its JSON request body.
- **Order return route** (`https://api.integrator.io/apis/v1/api/return`,
  REST) — plain REST `POST` used by `create_return`; sends
  `{orderId, quantity, fulfillmentLineItemId}` as the JSON request body
  (all three required) and carries no automatic retry (mutation).

The package provides a processor facade and MCP configuration for a host
runtime. It is not a standalone MCP server executable.

## Capabilities

The module registers 7 tools:

- `search_catalog` — product catalog search following the Shopify UCP
  convention. Pass a natural language `query` (e.g. "snowboard") with
  optional `limit`, `cursor`, `context`, `pagination`, and `meta`; returns
  the UCP envelope with `products` (title, description, price range,
  variants, availability, media) and `pagination`.
- `get_product` — complete product detail by identifier (`id`, e.g.
  `gid://shopify/Product/8184009359547`). Supports interactive variant
  narrowing via `selected` option selections and `preferences` relaxation
  order, plus optional `filters`, `context`, `signals`, and `attribution`.
  Returns the UCP envelope with the full `product` (variants with
  availability and media, options with availability signals, checkout URLs).
- `lookup_catalog` — batch lookup of products/variants by `ids`. Exposed per
  the UCP spec for completeness; the Celigo UCP proxy currently rejects
  well-formed `catalog.ids` requests, so prefer `get_product` for
  single-product retrieval.
- `search_shop_policies_and_faqs` — semantic search over shop policies and
  FAQs. Send a natural language `query` such as "what is your shipping
  policy"; the tool returns the matching `{question, answer}` records.
  Routed through the legacy endpoint automatically.
- `lookup_order` — order lookup via the Celigo integrator.io order REST API
  (`POST https://api.integrator.io/apis/v1/api/orders`, authenticated with the
  same Celigo bearer token). This is a plain REST route — not the JSON-RPC MCP
  proxy — so no UCP `meta` plumbing applies. Tool arguments are forwarded
  verbatim as the JSON request body (e.g. `order_id`, or the filter fields
  the target lookup integration expects); with no arguments the request is
  sent without a body. Responses are normalized to snake_case and an empty
  response becomes a friendly no-results string. **Live-verified**: the endpoint currently ignores supplied body fields and
  returns the shop's recent orders (last 3 at test time) with `page_info`
  paging; forwarded fields are kept for forward compatibility with filter
  support. Configurable via
  `celigo_mcp.orders_endpoint`.
- `create_return` — order return creation via the Celigo integrator.io REST API (`POST https://api.integrator.io/apis/v1/api/return`, same Celigo bearer token). Sends `{orderId, quantity, fulfillmentLineItemId}` built from the required `order_id`, `quantity`, and `fulfillment_line_item_id` arguments; unknown fields pass through verbatim. Empty responses become a friendly confirmation string. It is a mutation, so the tool carries no automatic retry. Configurable via `celigo_mcp.returns_endpoint`.
- `call_celigo_tool` — escape hatch to invoke any other Celigo
  integrator.io MCP tool by name (e.g. cart, checkout, and order operations
  such as `create_cart`, `get_cart`, `create_checkout`, `get_order` — these
  require Shopify buyer JWT authentication via `arguments.meta`). The tool
  name is a variable: pass `name` together with its `arguments` object.

UCP request metadata (`meta.ucp-agent.profile`) is injected automatically on
every call when the caller does not supply one, so hosts can call `get_product`
without knowing the UCP handshake:

```python
processor.get_product(id="gid://shopify/Product/8184009359547")
```

Cart, checkout, and order tools exist on the remote surface but are
buyer-scoped: Shopify rejects them with `AuthenticationRequired` unless the
request carries a valid buyer JWT. The bridge does not issue buyer JWTs; use
`call_celigo_tool` with `arguments.meta` carrying buyer identity once your
host owns buyer authentication.

## Architecture

`MCPCeligoBridge` delegates to a `CeligoClient`:

    MCP host
      -> MCP_CONFIGURATION
      -> MCPCeligoBridge
      -> CeligoClient
      -> UCP route    https://api.integrator.io/apis/v1/api/ucp/mcp   (catalog tools)
      -> legacy route https://api.integrator.io/apis/v1/api/mcp       (legacy_tools)
      -> orders route  https://api.integrator.io/apis/v1/api/orders  (lookup_order, REST)
      -> returns route https://api.integrator.io/apis/v1/api/return  (create_return, REST)

The client owns endpoint routing (tools listed in
`celigo_mcp.legacy_tools` go to the legacy endpoint, everything else to the
UCP endpoint), UCP meta injection, authentication, and retry handling. Tool
methods translate snake_case MCP arguments into JSON-RPC request envelopes,
parse the response payloads, and normalize keys to snake_case.

Response envelopes differ per route and are both handled:

- Legacy route: `{"result": "<json string>"}` — success payloads and backend
  rejections both arrive stringified; non-JSON rejections (gRPC-style
  messages) surface as errors. Trailing plain-text deprecation notices after
  the JSON payload are stripped automatically.
- UCP route: request echo with a `text` array of JSON-RPC messages
  (`result.content[].text` tool results, possibly `isError`-flagged) and/or
  an `errors` array (e.g. `AuthenticationRequired` rejections).

## Installation

Python 3.11 or later is required.

    python -m pip install -e ".[dev]"

`silvaengine-utility` must be available from the configured package source.

## Configuration

The host creates the processor with a logger and settings dictionary, then
assigns the request-specific endpoint and partition identifiers:

```python
import logging

from mcp_celigo_shopify_bridge import MCPCeligoBridge

settings = {
    "celigo_mcp": {
        "endpoint": "https://api.integrator.io/apis/v1/api/ucp/mcp",
        "legacy_endpoint": "https://api.integrator.io/apis/v1/api/mcp",
        "legacy_tools": ["search_shop_policies_and_faqs"],
        "orders_endpoint": "https://api.integrator.io/apis/v1/api/orders",
        "returns_endpoint": "https://api.integrator.io/apis/v1/api/return",
        "bearer_token": "replace-me",
    }
}

processor = MCPCeligoBridge(logging.getLogger(__name__), **settings)
processor.endpoint_id = "endpoint-id"
processor.part_id = "partition-id"
```

Optional settings: `ucp_agent_profile` (override the injected UCP agent
profile URL), `orders_endpoint` (override the order lookup REST URL),
`returns_endpoint` (override the order return REST URL),
`timeout`, `connect_timeout`, `max_retries`.

Set `bearer_token` to a Celigo integrator.io API token. Requests send
`Authorization: Bearer ***` and `Content-Type: application/json` headers.

## Usage

The MCP host loads:

```python
from mcp_celigo_shopify_bridge import MCP_CONFIGURATION, MCPCeligoBridge
```

Tool arguments use snake_case. `call_celigo_tool` requires `name` (the
Celigo MCP tool to invoke); `arguments` optionally carries the tool's own
argument object.

## Development

Run the local mocked test suite:

    python -m pytest -q
    python -m compileall -q mcp_celigo_shopify_bridge

The current tests mock HTTP execution. They verify tool registration,
argument mapping, endpoint routing, UCP meta injection, response parsing
(both envelopes), normalization, and error propagation. They do not validate
a live Celigo deployment, network authentication, or rate limiting behavior.
Use the live runner for that:

    python -m mcp_celigo_shopify_bridge.tests.run_integration

(credentials via `tests/.env`, see `.env.example`).

See [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) for implementation
status, ownership boundaries, verified remote behavior, and remaining
validation work.