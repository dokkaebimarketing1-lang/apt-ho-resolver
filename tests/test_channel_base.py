"""ChannelCollector Protocol + BaseChannel 단위 테스트."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.channels.base import BaseChannel, ChannelCollector


class _ConcreteChannel(BaseChannel):
    """BaseChannel 테스트용 구체 클래스."""
    channel_name = "test"
    reliability = 0.5

    def __init__(self, client: httpx.Client | None = None) -> None:
        super().__init__(api_key="test-key", client=client)

    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        if query.get("fail"):
            msg = query.get("fail", "")
            if msg == "timeout":
                raise httpx.TimeoutException("timeout", request=MagicMock())
            if msg == "http_error":
                resp = MagicMock(status_code=500)
                raise httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
            if msg == "connect_error":
                raise httpx.ConnectError("connect failed")
            if msg == "value_error":
                raise ValueError("unexpected")
        return query.get("items", [])


class TestChannelCollectorProtocol:
    """Protocol isinstance 검증."""

    def test_base_channel_satisfies_protocol(self) -> None:
        """Given BaseChannel subclass When isinstance check Then True"""
        ch = _ConcreteChannel()
        assert isinstance(ch, ChannelCollector)

    def test_protocol_requires_channel_name(self) -> None:
        """Given ChannelCollector Protocol Then 채널 인스턴스는 channel_name attr 보유"""
        ch = _ConcreteChannel()
        assert hasattr(ch, "channel_name")

    def test_protocol_requires_reliability(self) -> None:
        """Given ChannelCollector Protocol Then 채널 인스턴스는 reliability attr 보유"""
        ch = _ConcreteChannel()
        assert hasattr(ch, "reliability")

    def test_protocol_requires_collect(self) -> None:
        """Given ChannelCollector Protocol Then 채널 인스턴스는 collect 메서드 보유"""
        ch = _ConcreteChannel()
        assert callable(ch.collect)


class TestBaseChannelRetrySuccess:
    """BaseChannel 정상 호출 — 재시도 없이 성공."""

    def test_collect_returns_items(self) -> None:
        """Given 유효한 query When collect Then items 반환"""
        ch = _ConcreteChannel()
        expected = [{"id": 1}, {"id": 2}]
        result = ch.collect({"items": expected})
        assert result == expected

    def test_collect_empty_items(self) -> None:
        """Given 빈 items query When collect Then 빈 리스트"""
        ch = _ConcreteChannel()
        result = ch.collect({"items": []})
        assert result == []

    def test_collect_no_items_key(self) -> None:
        """Given items 없는 query When collect Then 빈 리스트 (기본값)"""
        ch = _ConcreteChannel()
        result = ch.collect({})
        assert result == []


class TestBaseChannelRetryErrors:
    """BaseChannel 에러 처리 — 재시도·백오프·폴백."""

    def test_retry_on_timeout_then_fallback(self) -> None:
        """Given 연속 TimeoutException When collect Then 3회 재시도 후 빈 리스트"""
        ch = _ConcreteChannel()
        with patch("time.sleep") as mock_sleep:
            result = ch.collect({"fail": "timeout"})
        assert result == []
        assert mock_sleep.call_count == 2  # attempt 0→1, 1→2 (attempt 2가 마지막)
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    def test_retry_on_http_error_then_fallback(self) -> None:
        """Given 연속 HTTPStatusError When collect Then 3회 재시도 후 빈 리스트"""
        ch = _ConcreteChannel()
        with patch("time.sleep"):
            result = ch.collect({"fail": "http_error"})
        assert result == []

    def test_retry_on_connect_error_then_fallback(self) -> None:
        """Given 연속 ConnectError When collect Then 3회 재시도 후 빈 리스트"""
        ch = _ConcreteChannel()
        with patch("time.sleep"):
            result = ch.collect({"fail": "connect_error"})
        assert result == []

    def test_value_error_no_retry(self) -> None:
        """Given ValueError(복구불가) When collect Then 즉시 빈 리스트, sleep 호출 없음"""
        ch = _ConcreteChannel()
        with patch("time.sleep") as mock_sleep:
            result = ch.collect({"fail": "value_error"})
        assert result == []
        mock_sleep.assert_not_called()

    def test_retry_then_success(self) -> None:
        """Given 2회 실패 → 3회 성공 When collect Then 성공 결과 반환"""
        call_count = 0

        class _RetryThenOk(BaseChannel):
            channel_name = "retry"
            reliability = 0.5

            def __init__(self) -> None:
                super().__init__(api_key="test")

            def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise httpx.TimeoutException("timeout", request=MagicMock())
                return [{"ok": True}]

        ch = _RetryThenOk()
        with patch("time.sleep"):
            result = ch.collect({})
        assert result == [{"ok": True}]
        assert call_count == 3

    def test_exponential_backoff_values(self) -> None:
        """Given 재시도 발생 When collect Then sleep 시간 = 2^attempt (1, 2)"""
        ch = _ConcreteChannel()
        sleep_times: list[float] = []

        def _fake_sleep(secs: float) -> None:
            sleep_times.append(secs)

        with patch("time.sleep", side_effect=_fake_sleep):
            ch.collect({"fail": "timeout"})
        assert sleep_times == [1.0, 2.0], f"Expected [1.0, 2.0], got {sleep_times}"
