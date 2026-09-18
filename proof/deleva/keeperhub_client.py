"""Reusable KeeperHub REST Direct Execution client.

Encapsulates authentication, request construction, idempotency-key handling,
simulation, execution, status polling, and error handling behind a small,
testable interface. This is the client every call to KeeperHub made during
this project's live proof work (simulate, execute, status, read) followed by
hand-built ``curl`` -- this module is that same, already-proven protocol,
made reusable.

HTTP is sent through an injectable ``Transport`` so tests never touch the
network: see ``tests/test_keeperhub_client.py`` for the fake transport used
there. The default transport uses only the standard library (no new
dependency).

Nothing in this module broadcasts by itself -- ``execute_contract_call`` and
``read_contract``/``simulate_contract_call`` all require the caller to invoke
them explicitly and, per KEEPERHUB_API_KEY, will fail loudly if no key is
configured.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


class KeeperHubError(Exception):
    """Raised for transport-level or genuinely-unexpected KeeperHub failures.

    A simulate call that reports ``wouldRevert: true`` is NOT this -- that is
    a normal, expected domain result and is returned as a SimulationResult,
    not raised. This is reserved for things like network failures, malformed
    responses, or HTTP errors the caller has no principled way to interpret
    as a simulation/execution outcome.
    """

    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class HttpResponse(Protocol):
    status_code: int
    body: dict


@dataclass(frozen=True)
class _HttpResponse:
    status_code: int
    body: dict


class Transport(Protocol):
    """Minimal HTTP transport interface. Tests inject a fake implementation."""

    def request(self, method: str, url: str, headers: dict[str, str], json_body: dict | None) -> _HttpResponse: ...


class UrllibTransport:
    """Default real transport, stdlib-only (no new dependency)."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout = timeout_seconds

    def request(self, method: str, url: str, headers: dict[str, str], json_body: dict | None) -> _HttpResponse:
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                status_code = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status_code = exc.code
        except urllib.error.URLError as exc:
            raise KeeperHubError(f"KeeperHub request failed: {exc.reason}") from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise KeeperHubError(
                f"KeeperHub returned non-JSON response (HTTP {status_code})", status_code=status_code, body=raw
            ) from exc

        return _HttpResponse(status_code=status_code, body=parsed)


@dataclass(frozen=True)
class SimulationResult:
    """Normalized result of a ``simulate: true`` contract-call request.

    ``success`` and ``would_revert`` are the two fields callers should branch
    on before ever considering a real execution: the documented safe
    sequence is "simulate, check wouldRevert is False, only then execute".
    """

    success: bool
    would_revert: bool | None
    gas_estimate: str | None
    error: str | None
    revert_reason: str | None
    raw: dict

    @property
    def is_safe_to_execute(self) -> bool:
        return self.success and self.would_revert is False


@dataclass(frozen=True)
class ExecutionResult:
    """Normalized result of an execute or status-poll call."""

    execution_id: str | None
    status: str | None  # "completed" | "failed" | "unconfirmed" | ... (open set, see KeeperHub docs)
    transaction_hash: str | None
    transaction_link: str | None
    error: str | None
    raw: dict

    @property
    def is_terminal(self) -> bool:
        """True once the execution has reached a final state.

        "unconfirmed" is explicitly non-terminal per KeeperHub's docs: the
        transaction broadcast but the receipt isn't conclusively read yet.
        Callers must keep polling the same executionId, never rotate the
        idempotency key or resend.
        """
        return self.status not in (None, "unconfirmed")

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"


class PollTimeoutError(KeeperHubError):
    """Raised when an execution never reaches a terminal status within the poll budget."""


def _parse_simulation(response: _HttpResponse) -> SimulationResult:
    body = response.body
    return SimulationResult(
        success=bool(body.get("success", response.status_code < 300)),
        would_revert=body.get("wouldRevert"),
        gas_estimate=body.get("gasEstimate"),
        error=body.get("error"),
        revert_reason=body.get("revertReason"),
        raw=body,
    )


def _parse_execution(response: _HttpResponse) -> ExecutionResult:
    body = response.body
    return ExecutionResult(
        execution_id=body.get("executionId"),
        status=body.get("status"),
        transaction_hash=body.get("transactionHash"),
        transaction_link=body.get("transactionLink"),
        error=body.get("error"),
        raw=body,
    )


class KeeperHubClient:
    """Thin, reusable client around KeeperHub's REST Direct Execution API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://app.keeperhub.com",
        transport: Transport | None = None,
        sleep_fn=time.sleep,
    ) -> None:
        if not api_key:
            raise KeeperHubError("KeeperHubClient requires a non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport or UrllibTransport()
        self._sleep = sleep_fn

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            # Without an explicit User-Agent, urllib sends its default
            # "Python-urllib/x.y" signature, which KeeperHub's Cloudflare
            # layer blocks outright (HTTP 403, Cloudflare error 1010,
            # "browser signature" ban) -- confirmed directly against the
            # real API. Any honest, non-default UA passes; this is not
            # spoofing a browser or another tool.
            "User-Agent": "deleva-backend/1.0",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _post(self, path: str, body: dict, *, idempotency_key: str | None = None) -> _HttpResponse:
        return self._transport.request(
            "POST", f"{self._base_url}{path}", self._headers(idempotency_key=idempotency_key), body
        )

    def _get(self, path: str) -> _HttpResponse:
        return self._transport.request("GET", f"{self._base_url}{path}", self._headers(), None)

    # -- contract-call: simulate / execute / read ---------------------------

    def simulate_contract_call(self, request: dict[str, Any]) -> SimulationResult:
        """Dry-run a KeeperHub contract-call request. Never broadcasts."""
        body = dict(request)
        body["simulate"] = True
        response = self._post("/api/execute/contract-call", body)
        return _parse_simulation(response)

    def execute_contract_call(
        self, request: dict[str, Any], *, idempotency_key: str | None = None
    ) -> ExecutionResult:
        """Broadcast a KeeperHub contract-call request.

        A fresh Idempotency-Key (UUID4) is generated automatically on every
        call unless the caller explicitly supplies one -- this is
        deliberate: a caller intending a genuinely new execution must never
        accidentally reuse the key from a prior simulate or execute call.
        Pass ``idempotency_key`` explicitly only when retrying an
        interrupted attempt at the *same* work.
        """
        body = dict(request)
        body.pop("simulate", None)
        key = idempotency_key or str(uuid.uuid4())
        response = self._post("/api/execute/contract-call", body, idempotency_key=key)
        return _parse_execution(response)

    def read_contract(
        self, *, contract_address: str, chain_id: int, function_name: str, function_args: str, abi: str
    ) -> Any:
        """Call a view/pure function. Returns the decoded result directly (no signing, no broadcast)."""
        body = {
            "contractAddress": contract_address,
            "chainId": chain_id,
            "functionName": function_name,
            "functionArgs": function_args,
            "abi": abi,
        }
        response = self._post("/api/execute/contract-call", body)
        if response.status_code >= 300:
            raise KeeperHubError(
                f"KeeperHub read_contract failed (HTTP {response.status_code}): {response.body}",
                status_code=response.status_code,
                body=response.body,
            )
        return response.body.get("result")

    # -- status -----------------------------------------------------------

    def get_execution_status(self, execution_id: str) -> ExecutionResult:
        response = self._get(f"/api/execute/{execution_id}/status")
        return _parse_execution(response)

    def poll_execution_status(
        self, execution_id: str, *, max_attempts: int = 10, poll_interval_seconds: float = 2.0
    ) -> ExecutionResult:
        """Poll until the execution reaches a terminal status, or raise PollTimeoutError.

        Never rotates the idempotency key and never re-sends the execute
        request -- polling only ever reads status for the same executionId,
        matching KeeperHub's documented "unconfirmed is not a failure, do
        not resend" guidance.
        """
        last: ExecutionResult | None = None
        for attempt in range(max_attempts):
            last = self.get_execution_status(execution_id)
            if last.is_terminal:
                return last
            if attempt < max_attempts - 1:
                self._sleep(poll_interval_seconds)
        raise PollTimeoutError(
            f"execution {execution_id} did not reach a terminal status after {max_attempts} attempts",
            body=last.raw if last else None,
        )

    def execute_and_wait(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 10,
        poll_interval_seconds: float = 2.0,
    ) -> ExecutionResult:
        """Execute, then poll to a terminal status if the initial response was non-terminal."""
        result = self.execute_contract_call(request, idempotency_key=idempotency_key)
        if result.is_terminal or not result.execution_id:
            return result
        return self.poll_execution_status(
            result.execution_id, max_attempts=max_attempts, poll_interval_seconds=poll_interval_seconds
        )
