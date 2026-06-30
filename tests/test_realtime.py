"""Supabase Realtime 구독 단위 테스트 — mock 이벤트, 실제 연결 없음.

테스트 범위:
1. subscribe_ho_state: 콜백 등록 및 호출
2. handle_event: ho_state 변경 이벤트 → 일치 콜백 호출
3. handle_event: line_fact 변경 이벤트 → 일치 콜백 호출
4. handle_event: evidence_log 대량 insert → 무시 (구독 금지)
5. unsubscribe: 구독 해제 후 이벤트 무시
"""

from __future__ import annotations

from typing import Any

from src.realtime import RealtimeSubscriber


def _make_event(table: str, event_type: str = "INSERT", **extra: Any) -> dict[str, Any]:
    """헬퍼: Realtime 이벤트 딕셔너리 생성."""
    return {
        "table": table,
        "event_type": event_type,
        "schema": "public",
        **extra,
    }


class TestRealtimeSubscriber:
    """RealtimeSubscriber 구독/알림 단위 테스트."""

    def test_subscribe_ho_state(self) -> None:
        """Given RealtimeSubscriber
        When subscribe_ho_state(callback)
        Then 호_state 이벤트 전송 시 콜백 호출됨"""
        sub = RealtimeSubscriber("test-channel")
        calls: list[dict[str, Any]] = []

        def callback(event: dict[str, Any]) -> None:
            calls.append(event)

        sub.subscribe_ho_state(callback)
        result = sub.handle_event(_make_event("ho_state"))

        assert result == ["callback"]
        assert len(calls) == 1
        assert calls[0]["table"] == "ho_state"

    def test_handle_event_ho_state_record(self) -> None:
        """Given ho_state 구독 등록
        When handle_event(ho_state 이벤트)
        Then 콜백에 정확한 이벤트 데이터 전달"""
        sub = RealtimeSubscriber("test-channel")
        received: list[dict[str, Any]] = []

        def on_change(event: dict[str, Any]) -> None:
            received.append(event)

        sub.subscribe_ho_state(on_change)
        event = _make_event("ho_state", record={"ho_id": "1503", "status": "occupied"})
        result = sub.handle_event(event)

        assert result == ["on_change"]
        assert len(received) == 1
        assert received[0]["record"]["ho_id"] == "1503"
        assert received[0]["record"]["status"] == "occupied"
        assert received[0]["event_type"] == "INSERT"

    def test_handle_event_line_fact(self) -> None:
        """Given line_fact 구독 등록
        When handle_event(line_fact 이벤트)
        Then 콜백에 line_fact 데이터 전달"""
        sub = RealtimeSubscriber("test-channel")
        received: list[dict[str, Any]] = []

        def on_line(event: dict[str, Any]) -> None:
            received.append(event)

        sub.subscribe_line_fact(on_line)
        event = _make_event("line_fact", record={"line_id": "101-01", "area_cm2": 845000})
        result = sub.handle_event(event)

        assert result == ["on_line"]
        assert len(received) == 1
        assert received[0]["record"]["line_id"] == "101-01"

    def test_handle_event_evidence_log_ignored(self) -> None:
        """Given ho_state + line_fact 구독 등록
        When handle_event(evidence_log 이벤트)
        Then 콜백 호출 안 됨 (구독 금지)"""
        sub = RealtimeSubscriber("test-channel")
        calls: list[dict[str, Any]] = []

        def callback(event: dict[str, Any]) -> None:
            calls.append(event)

        sub.subscribe_ho_state(callback)
        sub.subscribe_line_fact(callback)

        event = _make_event("evidence_log", record={"count": 10000, "operation": "bulk_insert"})
        result = sub.handle_event(event)

        assert result == []
        assert len(calls) == 0

    def test_unsubscribe_then_ignore(self) -> None:
        """Given 구독 등록 후 unsubscribe 호출
        When handle_event(ho_state 이벤트)
        Then 콜백 호출 안 됨"""
        sub = RealtimeSubscriber("test-channel")
        calls: list[dict[str, Any]] = []

        def callback(event: dict[str, Any]) -> None:
            calls.append(event)

        sub.subscribe_ho_state(callback)
        sub.unsubscribe("test-channel")

        event = _make_event("ho_state", record={"ho_id": "1503"})
        result = sub.handle_event(event)

        assert result == []
        assert len(calls) == 0
