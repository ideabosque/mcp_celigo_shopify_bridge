# Development Plan — MCP Celigo Shopify Bridge

## Purpose

`mcp_celigo_shopify_bridge` adapts the Celigo integrator.io MCP proxy into
tools for a SilvaEngine MCP host. It is a library integration point: process
lifecycle, MCP transport, credentials, and endpoint/partition selection
belong to the host runtime.

The proxy has two routes, both JSON-RPC 2.0 over HTTP POST with
`Authorization: Bearer <Celigo token>`:

- **UCP route** `https://api.integrator.io/apis/v1/api/ucp/mcp` — primary;
  proxies the Shopify Storefront MCP's UCP-conforming tools. UCP tools
  require `arguments.meta.ucp-agent.profile` (injected automatically by the
  client when omitted). Response envelope: request echo with a `text` array
  of JSON-RPC messages (`result.content[].text`, possibly `isError`) and/or
  an `errors` array whose entries carry stringified JSON-RPC error bodies.
- **Legacy route** `https://api.integrator.io/apis/v1/api/mcp` — legacy
  Storefront MCP tools behind a stringified `{"result": "<json string>"}`
  envelope. Success payloads and backend rejections both arrive stringified;
  non-JSON rejections are gRPC-style messages.

`tools/list` and `initialize` are not supported by either route (the UCP
proxy answers every non-`tools/call` method with `-32602 Tool not found`);
the tool surface is declared locally in `mcp_configuration.py`.

## Implemented

- 5 tool schemas + 5 module links: `search_catalog`, `get_product`,
  `lookup_catalog`, `search_shop_policies_and_faqs`, `call_celigo_tool`
  (generic invoker — the remote tool `name` is a caller-supplied variable,
  forwarded verbatim in JSON-RPC `params.name` with its `arguments` object)
- Single facade `MCPCeligoBridge` over `CeligoBackedProcessor`
- `CeligoClient`: JSON-RPC `tools/call` over `httpx` HTTP/2, Bearer auth,
  configurable timeout/retries, per-tool endpoint routing
  (`celigo_mcp.legacy_tools` → legacy endpoint, everything else → UCP
  endpoint), automatic `meta.ucp-agent` injection, both response envelopes
  parsed, camelCase → snake_case normalization
- `error_handler.py`: `@handle_errors` decorator, Celigo error codes
  (`JSONRPC_REQUEST_FAILED`, `CELIGO_API_ERROR`, `API_CONNECTION_FAILED`),
  validators
- Unit tests (mocked HTTP): tool registration, argument mapping, endpoint
  routing, meta injection, response parsing/normalization, error propagation
- Live integration runner: `python -m mcp_celigo_shopify_bridge.tests.run_integration`
  (credentials via `tests/.env`, see `.env.example`)

## Tool Surface

| Area | Tools |
|---|---|
| Catalog (UCP route) | `search_catalog`, `get_product`, `lookup_catalog` |
| Policies & FAQs (legacy route) | `search_shop_policies_and_faqs` |
| Generic invocation | `call_celigo_tool` |

### Verified remote behavior (live probes, October 2026)

| Tool | Endpoint | Arguments | Behavior |
|---|---|---|---|
| `search_catalog` | UCP | `{"catalog": {"query": "...", "pagination": {"limit": N}}}` + `meta` | Works — full UCP envelope (`products`, `pagination`) |
| `get_product` | UCP | `{"catalog": {"id": "gid://shopify/Product/<id>"}}` + `meta` | Works — full UCP envelope with `product` detail |
| `lookup_catalog` | UCP | `{"catalog": {"ids": [...]}}` + `meta` | Celigo proxy rejects well-formed requests ("missing required properties: ids") — proxy-side bug, exposed but not usable |
| `search_shop_policies_and_faqs` | legacy | `{"query": "...", "limit": N}` | Works — `[{question, answer}, ...]` |
| `search_shop_policies_and_faqs` | UCP | — | `AuthenticationRequired` — buyer JWT gated |
| cart/checkout/order tools | UCP | — | Reach Shopify but are buyer-JWT-gated (`create_cart`/`get_checkout` also error with "Missing required arguments" when the proxy fails to map args) |

Request shapes follow the UCP 2026-08-25 spec
(`https://ucp.dev/2026-08-25/services/shopping/mcp.openrpc.json` and the
`catalog_lookup.json` / `cart.json` / `checkout.json` schemas); `meta` is
required and carries `ucp-agent.profile`.

The legacy catalog tools are dead: since the August 31, 2026 Storefront MCP
deprecation they return HTTP 200 with an empty body. Catalog traffic must use
the UCP route.

## Ownership Boundaries

- **This package owns**: tool schemas, module links, argument validation,
  JSON-RPC envelope construction, per-tool endpoint routing, UCP meta
  injection, response parsing/normalization, error mapping.
- **The host runtime owns**: processor instantiation, endpoint/partition
  assignment (`endpoint_id`, `part_id`), credentials storage, MCP transport,
  and buyer authentication (JWTs for cart/checkout/order tools if used).
- **Celigo owns**: the MCP proxy behavior, the Bearer token lifecycle, and
  the underlying commerce data.

## Remaining Validation Work

- Confirm `limit` argument behavior against the live endpoint (currently
  passed through; backend may ignore it).
- Re-test `lookup_catalog` once Celigo fixes the proxy's argument mapping
  (tracked via the "missing required properties: ids" rejection).
- Monitor gRPC-style rejection modes on the legacy route (e.g. transient
  backend errors observed as `3:query is required` under load) and tune
  `max_retries`.
- If buyer JWT authentication is needed for cart/checkout/order tools, the
  host must supply `meta` with buyer identity; consider a dedicated mixin
  when a concrete deployment needs it.
- If Celigo adds more MCP tools, extend `mcp_configuration.py`, add a mixin,
  and follow the same test pattern.