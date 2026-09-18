from __future__ import annotations

from collections import deque

import pytest

from deleva.keeperhub_client import (
    KeeperHubClient,
    KeeperHubError,
    PollTimeoutError,
    _HttpResponse,
)


class FakeTransport:
    """Records every request made and returns pre-programmed canned responses.
    No network access -- this is the only transport used in this test file."""

    def __init__(self, responses: list[_HttpResponse]):
        self._responses = deque(responses)
        self.calls: list[dict] = []

    def request(self, method, url, headers, json_body):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "json_body": json_body})
        if not self._responses:
            raise AssertionError("FakeTransport ran out of programmed responses")
        return self._responses.popleft()


class FakeSleep:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_client(responses: list[_HttpResponse], sleep_fn=None) -> tuple[KeeperHubClient, FakeTransport]:
    transport = FakeTransport(responses)
    client = KeeperHubClient(
        api_key="kh_test_key", base_url="https://app.keeperhub.com", transport=transport, sleep_fn=sleep_fn or (lambda s: None)
    )
    return client, transport


class TestClientConstruction:
    def test_requires_non_empty_api_key(self):
        with pytest.raises(KeeperHubError):
            KeeperHubClient(api_key="")


class TestSimulation:
    def test_successful_simulation_result(self):
        client, transport = make_client(
            [_HttpResponse(200, {"success": True, "wouldRevert": False, "gasEstimate": "56240"})]
        )
        result = client.simulate_contract_call({"contractAddress": "0xUSDC", "chainId": 8453})
        assert result.success is True
        assert result.would_revert is False
        assert result.is_safe_to_execute is True
        assert result.gas_estimate == "56240"

    def test_failed_simulation_result_is_not_raised(self):
        client, transport = make_client(
            [
                _HttpResponse(
                    400,
                    {
                        "success": False,
                        "wouldRevert": True,
                        "failureKind": "revert",
                        "revertReason": "ERC20: transfer amount exceeds allowance",
                    },
                )
            ]
        )
        # A reverting simulation is a normal domain result, not an exception.
        result = client.simulate_contract_call({"contractAddress": "0xPool", "chainId": 8453})
        assert result.success is False
        assert result.would_revert is True
        assert result.is_safe_to_execute is False
        assert "allowance" in result.revert_reason

    def test_simulate_always_sets_simulate_true_in_request_body(self):
        client, transport = make_client([_HttpResponse(200, {"success": True, "wouldRevert": False})])
        client.simulate_contract_call({"contractAddress": "0xUSDC", "chainId": 8453, "simulate": False})
        assert transport.calls[0]["json_body"]["simulate"] is True

    def test_simulate_sends_no_idempotency_key_header(self):
        client, transport = make_client([_HttpResponse(200, {"success": True, "wouldRevert": False})])
        client.simulate_contract_call({"contractAddress": "0xUSDC", "chainId": 8453})
        assert "Idempotency-Key" not in transport.calls[0]["headers"]


class TestExecution:
    def test_execute_generates_a_fresh_idempotency_key_each_call(self):
        client, transport = make_client(
            [
                _HttpResponse(202, {"executionId": "exec1", "status": "completed", "transactionHash": "0xaaa"}),
                _HttpResponse(202, {"executionId": "exec2", "status": "completed", "transactionHash": "0xbbb"}),
            ]
        )
        client.execute_contract_call({"contractAddress": "0xUSDC", "chainId": 8453})
        client.execute_contract_call({"contractAddress": "0xUSDC", "chainId": 8453})

        key1 = transport.calls[0]["headers"]["Idempotency-Key"]
        key2 = transport.calls[1]["headers"]["Idempotency-Key"]
        assert key1 != key2
        assert key1 and key2  # both non-empty

    def test_execute_never_sends_simulate_true(self):
        client, transport = make_client(
            [_HttpResponse(202, {"executionId": "exec1", "status": "completed"})]
        )
        client.execute_contract_call({"contractAddress": "0xUSDC", "chainId": 8453, "simulate": True})
        assert "simulate" not in transport.calls[0]["json_body"]

    def test_execute_honors_an_explicitly_supplied_idempotency_key(self):
        client, transport = make_client([_HttpResponse(202, {"executionId": "exec1", "status": "completed"})])
        client.execute_contract_call({"contractAddress": "0xUSDC", "chainId": 8453}, idempotency_key="my-fixed-key")
        assert transport.calls[0]["headers"]["Idempotency-Key"] == "my-fixed-key"

    def test_successful_execution_result(self):
        client, transport = make_client(
            [
                _HttpResponse(
                    202,
                    {
                        "executionId": "za25idtoxl42mtyfjmbks",
                        "status": "completed",
                        "transactionHash": "0xd36217b09ba81cea624e88e756514f2ebc0dc689a20dad4286d6f852f205ec57",
                    },
                )
            ]
        )
        result = client.execute_contract_call({"contractAddress": "0xPool", "chainId": 8453})
        assert result.succeeded is True
        assert result.is_terminal is True
        assert result.execution_id == "za25idtoxl42mtyfjmbks"
        assert result.transaction_hash.startswith("0xd36217b0")

    def test_failed_execution_result(self):
        client, transport = make_client(
            [_HttpResponse(400, {"executionId": "exec1", "status": "failed", "error": "execution reverted"})]
        )
        result = client.execute_contract_call({"contractAddress": "0xPool", "chainId": 8453})
        assert result.succeeded is False
        assert result.is_terminal is True
        assert result.status == "failed"


class TestStatusPolling:
    def test_unconfirmed_then_completed_polls_to_terminal(self):
        fake_sleep = FakeSleep()
        client, transport = make_client(
            [
                _HttpResponse(200, {"executionId": "exec1", "status": "unconfirmed"}),
                _HttpResponse(200, {"executionId": "exec1", "status": "unconfirmed"}),
                _HttpResponse(
                    200, {"executionId": "exec1", "status": "completed", "transactionHash": "0xabc"}
                ),
            ],
            sleep_fn=fake_sleep,
        )
        result = client.poll_execution_status("exec1", max_attempts=5, poll_interval_seconds=2.0)
        assert result.status == "completed"
        assert result.is_terminal is True
        assert len(transport.calls) == 3
        # Slept between attempt 1->2 and 2->3, not after the terminal result.
        assert fake_sleep.calls == [2.0, 2.0]

    def test_poll_times_out_if_never_terminal(self):
        client, transport = make_client(
            [_HttpResponse(200, {"executionId": "exec1", "status": "unconfirmed"}) for _ in range(3)]
        )
        with pytest.raises(PollTimeoutError):
            client.poll_execution_status("exec1", max_attempts=3, poll_interval_seconds=0)

    def test_poll_never_rotates_idempotency_key_or_resends(self):
        # Polling only ever GETs status -- it must never POST an execute
        # request, per KeeperHub's documented "do not resend on unconfirmed".
        client, transport = make_client(
            [
                _HttpResponse(200, {"executionId": "exec1", "status": "unconfirmed"}),
                _HttpResponse(200, {"executionId": "exec1", "status": "completed"}),
            ]
        )
        client.poll_execution_status("exec1", max_attempts=5, poll_interval_seconds=0)
        assert all(call["method"] == "GET" for call in transport.calls)

    def test_execute_and_wait_polls_when_initial_response_is_unconfirmed(self):
        client, transport = make_client(
            [
                _HttpResponse(202, {"executionId": "exec1", "status": "unconfirmed"}),
                _HttpResponse(200, {"executionId": "exec1", "status": "completed", "transactionHash": "0xabc"}),
            ]
        )
        result = client.execute_and_wait({"contractAddress": "0xPool", "chainId": 8453}, poll_interval_seconds=0)
        assert result.succeeded is True
        assert result.transaction_hash == "0xabc"

    def test_execute_and_wait_returns_immediately_when_already_terminal(self):
        client, transport = make_client(
            [_HttpResponse(202, {"executionId": "exec1", "status": "completed", "transactionHash": "0xabc"})]
        )
        result = client.execute_and_wait({"contractAddress": "0xPool", "chainId": 8453})
        assert result.succeeded is True
        assert len(transport.calls) == 1  # no status-poll GET needed
