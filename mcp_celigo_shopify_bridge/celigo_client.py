#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celigo MCP Client for MCP Celigo Shopify Bridge

Handles JSON-RPC 2.0 `tools/call` execution via HTTP POST against the Celigo
integrator.io MCP proxy.

Two Celigo routes exist and behave differently:

- UCP route ``https://api.integrator.io/apis/v1/api/ucp/mcp`` — proxies the
  Shopify Storefront MCP UCP-conforming tools (search_catalog, get_product).
  Envelope: request echo + ``text`` array of JSON-RPC result messages
  (``result.content[].text``) and/or an ``errors`` array; UCP tools require
  request ``meta.ucp-agent.profile``.
- Legacy route ``https://api.integrator.io/apis/v1/api/mcp`` — legacy
  Storefront MCP tools behind a stringified ``{"result": "<json string>"}``
  envelope. ``search_shop_policies_and_faqs`` still works here; the legacy
  catalog tools died with the August 31, 2026 deprecation (empty bodies).

Tools listed in ``celigo_mcp.legacy_tools`` are routed to the legacy endpoint
(everything else goes to the primary UCP endpoint), and ``meta.ucp-agent``
profile metadata is injected automatically when the caller does not supply it.
"""

from __future__ import annotations

__author__ = "Idea Bosque"

import json
import logging
import traceback
from typing import Any, Dict, Optional, Tuple

import httpx
import humps

from silvaengine_utility import convert_decimal_to_number

from .error_handler import ErrorCode, CeligoError, build_error_response


class CeligoClient:
    """JSON-RPC client for the Celigo integrator.io MCP proxy.

    Auth is a static Celigo Bearer token supplied via
    ``setting["celigo_mcp"]["bearer_token"]``. The primary endpoint defaults
    to the UCP route and may be overridden via
    ``setting["celigo_mcp"]["endpoint"]``; legacy-routed tools go to
    ``setting["celigo_mcp"]["legacy_endpoint"]`` (default: the legacy
    integrator.io MCP URL) when listed in
    ``setting["celigo_mcp"]["legacy_tools"]``.
    """

    _DEFAULT_ENDPOINT = "https://api.integrator.io/apis/v1/api/ucp/mcp"
    _DEFAULT_LEGACY_ENDPOINT = "https://api.integrator.io/apis/v1/api/mcp"
    _DEFAULT_UCP_PROFILE = (
        "https://shopify.dev/ucp/agent-profiles/examples/"
        "2026-08-25/valid-with-capabilities.json"
    )
    # Tools proxied only by the legacy route. Catalog tools MUST stay on the
    # UCP route: the legacy ones return empty bodies post-deprecation, and
    # search_shop_policies_and_faqs is JWT-gated on the UCP route.
    _DEFAULT_LEGACY_TOOLS = ("search_shop_policies_and_faqs",)
    _DEFAULT_TIMEOUT = 60.0
    _DEFAULT_CONNECT_TIMEOUT = 15.0

    def __init__(self, logger: logging.Logger, **setting: Dict[str, Any]):
        self.logger = logger
        self.setting = setting
        self.endpoint_id = None
        self.part_id = None

        module_setting = setting.get("celigo_mcp", {}) or {}
        self._endpoint = module_setting.get("endpoint") or self._DEFAULT_ENDPOINT
        self._bearer_token = module_setting.get("bearer_token")
        self._legacy_endpoint = (
            module_setting.get("legacy_endpoint") or self._DEFAULT_LEGACY_ENDPOINT
        )
        legacy_tools = module_setting.get("legacy_tools", self._DEFAULT_LEGACY_TOOLS)
        self._legacy_tools = (
            set(legacy_tools)
            if isinstance(legacy_tools, (list, tuple, set))
            else set(self._DEFAULT_LEGACY_TOOLS)
        )
        self._ucp_profile = (
            module_setting.get("ucp_agent_profile") or self._DEFAULT_UCP_PROFILE
        )
        self._timeout = float(module_setting.get("timeout", self._DEFAULT_TIMEOUT))
        self._connect_timeout = float(
            module_setting.get("connect_timeout", self._DEFAULT_CONNECT_TIMEOUT)
        )
        self._max_retries = int(module_setting.get("max_retries", 1))
        self._http_client = httpx.Client(
            http2=True,
            timeout=httpx.Timeout(self._timeout, connect=self._connect_timeout),
        )

    # ==================== Request Execution ====================

    def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """Invoke a Celigo MCP tool via JSON-RPC ``tools/call``.

        Builds the JSON-RPC envelope::

            {"jsonrpc": "2.0", "method": "tools/call", "id": 1,
             "params": {"name": <tool_name>, "arguments": <arguments>}}

        Injects ``arguments.meta.ucp-agent.profile`` when the caller has not
        supplied one (required by UCP-conforming tools), routes legacy tools
        to the legacy endpoint, posts with ``Authorization: Bearer ***``, and
        normalizes both the legacy stringified ``result`` envelope and the
        UCP proxy ``text``/``errors`` envelope.
        """
        endpoint_id = self.endpoint_id
        if endpoint_id:
            # Reserved for host-side endpoint interpolation; the production
            # Celigo endpoints are static, so this is a no-op today.
            url = self._endpoint
        else:
            url = self._endpoint

        # Legacy-only tools (e.g. search_shop_policies_and_faqs) proxy through
        # the legacy route; everything else targets the primary UCP endpoint.
        if tool_name in self._legacy_tools and self._legacy_endpoint:
            url = self._legacy_endpoint

        arguments = self._with_ucp_meta(arguments)

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1,
            "params": {"name": tool_name, "arguments": arguments or {}},
        }

        headers = {
            "Authorization": f"Bearer {self._bearer_token}" if self._bearer_token else None,
            "Content-Type": "application/json",
        }
        headers = {k: v for k, v in headers.items() if v is not None}

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http_client.post(
                    url,
                    json=payload,
                    headers=headers,
                )
                return self._handle_response(response)
            except CeligoError:
                raise
            except Exception as exception:
                last_error = exception
                self.logger.warning(
                    f"Celigo request attempt {attempt + 1} failed: {exception}"
                )
                if attempt >= self._max_retries:
                    break
                continue

        self.logger.error(
            f"Failed to call Celigo tool {tool_name}: {last_error}\n"
            f"{traceback.format_exc()}"
        )
        return build_error_response(
            message=str(last_error),
            error_code=ErrorCode.API_CONNECTION_FAILED,
        )

    def _with_ucp_meta(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure ``arguments.meta.ucp-agent.profile`` is present.

        UCP-conforming tools require agent identification metadata; callers
        may supply their own profile URL, otherwise the configured default
        (Shopify example agent profile) is injected. Caller-supplied values
        are never clobbered.
        """
        arguments = dict(arguments or {})
        meta = arguments.get("meta")
        meta = dict(meta) if isinstance(meta, dict) else {}
        agent = meta.get("ucp-agent")
        agent = dict(agent) if isinstance(agent, dict) else {}
        if not agent.get("profile"):
            agent.setdefault("profile", self._ucp_profile)
            meta["ucp-agent"] = agent
            arguments["meta"] = meta
        return arguments

    # ==================== Response Handling ====================

    def _handle_response(self, response: httpx.Response) -> Any:
        """Normalize a Celigo JSON-RPC HTTP response into Python data.

        Two envelope shapes are handled:

        - UCP proxy envelope: ``{"text": [<jsonrpc message>, ...], "errors":
          [...]}`` — unwrapped via :meth:`_handle_ucp_envelope`.
        - Legacy envelope: ``{"result": "<json string>"}`` — the stringified
          payload is parsed. gRPC-style error strings inside ``result`` are
          surfaced as Celigo errors. HTTP errors raise :class:`CeligoError`.
        """
        if response.status_code >= 400:
            raise CeligoError(
                message=f"Celigo API returned HTTP {response.status_code}: "
                f"{response.text[:500]}",
                error_code=ErrorCode.CELIGO_API_ERROR,
                details={"status_code": response.status_code},
            )

        # Some Celigo MCP tools return an empty body on success (observed
        # with legacy Storefront MCP get_product/lookup_catalog over the
        # proxy after the August 31, 2026 deprecation).
        if not (response.content is None or len(response.content) == 0):
            try:
                body = response.json()
            except Exception as exception:
                raise CeligoError(
                    message=f"Celigo API returned non-JSON response: {exception}",
                    error_code=ErrorCode.JSONRPC_REQUEST_FAILED,
                )
        else:
            return []

        # Celigo UCP proxy envelope ("text" array of JSON-RPC messages and/or
        # Celigo-level "errors" array). Unwrap before legacy handling.
        if isinstance(body, dict) and (
            isinstance(body.get("text"), list) or isinstance(body.get("errors"), list)
        ):
            return self._handle_ucp_envelope(body)

        # JSON-RPC error envelope: {"error": {"code": ..., "message": ...}}
        if isinstance(body, dict) and "error" in body and "result" not in body:
            error = body["error"]
            message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise CeligoError(
                message=message,
                error_code=ErrorCode.CELIGO_API_ERROR,
                details={"code": error.get("code") if isinstance(error, dict) else None},
            )

        result = body.get("result") if isinstance(body, dict) else None

        # Success payloads and backend rejections both arrive stringified
        # under "result". Parse when possible; otherwise treat as an error
        # string (e.g. gRPC "query is required" rejections).
        if isinstance(result, str):
            parsed = self._parse_result_string(result)
            if parsed is None:
                raise CeligoError(
                    message=result,
                    error_code=ErrorCode.CELIGO_API_ERROR,
                )
            return self._normalize(parsed)

        if result is None:
            raise CeligoError(
                message="Celigo API returned an empty result",
                error_code=ErrorCode.CELIGO_API_ERROR,
            )

        return self._normalize(result)

    def _handle_ucp_envelope(self, body: dict) -> Any:
        """Unwrap the Celigo UCP proxy envelope into Python data.

        Shape (verified live)::

            {"jsonrpc": "2.0", "method": ..., "id": ..., "params": {...},
             "text": [{"jsonrpc": "2.0", "id": 1, "result": {"content":
                       [{"type": "text", "text": "<json string>"}]}}],
             "errors": [{"code": 403, "message": "<jsonrpc error json>"}]}

        ``errors`` entries carry a stringified JSON-RPC error as their
        ``message`` (e.g. the Shopify ``AuthenticationRequired`` rejection for
        buyer-scoped tools); ``text`` entries carry either a JSON-RPC error
        (``error.code``) or a tool result whose content blocks hold the
        payload — optionally flagged ``isError`` for backend rejections.
        """
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            message, details = self._extract_ucp_error(errors)
            raise CeligoError(
                message=message,
                error_code=ErrorCode.CELIGO_API_ERROR,
                details=details,
            )

        payload: Any = None
        for message in body.get("text") or []:
            if not isinstance(message, dict):
                continue
            if isinstance(message.get("error"), dict):
                rpc_error = message["error"]
                raise CeligoError(
                    message=str(rpc_error.get("message") or rpc_error),
                    error_code=ErrorCode.CELIGO_API_ERROR,
                    details={
                        "code": rpc_error.get("code"),
                        "data": rpc_error.get("data"),
                    },
                )
            result = message.get("result")
            if not isinstance(result, dict):
                continue
            text = self._first_content_text(result)
            if text is None:
                continue
            if result.get("isError"):
                # Backend rejection surfaced as an error content block
                # (e.g. "Missing required arguments: id").
                raise CeligoError(
                    message=text,
                    error_code=ErrorCode.CELIGO_API_ERROR,
                )
            parsed = self._parse_result_string(text)
            if parsed is None:
                parsed = text
            payload = (
                self._normalize(parsed)
                if isinstance(parsed, (dict, list))
                else parsed
            )
            break

        if payload is None:
            raise CeligoError(
                message="Celigo UCP response contained no tool result",
                error_code=ErrorCode.JSONRPC_REQUEST_FAILED,
            )
        return payload

    @staticmethod
    def _first_content_text(result: dict) -> Optional[str]:
        """Return the first string ``content[].text`` block, if any."""
        content = result.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    return block["text"]
        return None

    @staticmethod
    def _extract_ucp_error(errors: list) -> Tuple[str, Dict[str, Any]]:
        """Extract a message from a Celigo-level ``errors`` array entry.

        The first entry's ``message`` is usually a stringified JSON-RPC error
        body, e.g. ``{"jsonrpc": "2.0", "id": 1, "error": {"code": -32000,
        "message": "AuthenticationRequired", "data": "Unauthorized: ..."}}``.
        Falls back to the raw string when parsing fails.
        """
        first = errors[0]
        inner = first.get("message") if isinstance(first, dict) else None
        inner = str(inner) if inner else str(first)
        try:
            parsed = json.loads(inner)
        except Exception:
            return inner, {}
        error = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or error)
            data = error.get("data")
            if isinstance(data, str) and data:
                message = f"{message} — {data}"
            details: Dict[str, Any] = {}
            if isinstance(first, dict) and first.get("code") is not None:
                details["status_code"] = first.get("code")
            if error.get("code") is not None:
                details["code"] = error.get("code")
            return message, details
        return inner, {}

    def _parse_result_string(self, result: str) -> Any:
        """Parse the stringified result payload; ``None`` when not JSON.

        The Shopify Storefront MCP appends a plain-text deprecation notice
        after the JSON payload (e.g.
        ``...,\"instructions\":\"...\"},DEPRECATION NOTICE: This tool is served
        by the Storefront MCP server...``). Balance the braces to recover the
        leading JSON value and drop the trailing notice.
        """
        text = result.strip()
        if not text:
            return None

        candidate = text
        if candidate.startswith(("[", "{")):
            candidate = self._strip_trailing_notice(text)

        if not (candidate.startswith("[") or candidate.startswith("{") or candidate.startswith('"')):
            return None
        try:
            return json.loads(candidate)
        except Exception:
            return None

    @staticmethod
    def _strip_trailing_notice(text: str) -> str:
        """Cut a stringified payload at the end of its first JSON value.

        Walks the text tracking string literals and brace/bracket depth; the
        JSON value ends where the depth returns to zero.
        """
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
                if depth == 0:
                    return text[: index + 1]
        return text

    def _normalize(self, data: Any) -> Any:
        """Convert camelCase keys to snake_case and decimals to numbers."""
        if isinstance(data, dict):
            return {
                humps.decamelize(key): self._normalize(value)
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [self._normalize(item) for item in data]
        return convert_decimal_to_number(data)