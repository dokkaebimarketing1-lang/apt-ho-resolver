"""Supabase Realtime 구독 — ho_state/line_fact 변경 알림.

설계:
- 소규모 운영 이벤트만 구독 (ho_state 상태 변경, line_fact 신규 학습).
- evidence_log 대량 insert는 구독 금지 (무시).
- supabase-py channel().on('postgres_changes', ...).subscribe() 패턴.
- 실제 Supabase 연결은 외부에서 주입 (테스트는 mock 이벤트로만).
"""

from __future__ import annotations

from typing import Any, Callable


class RealtimeSubscriber:
    """Supabase Realtime 채널 구독 관리.

    Args:
        channel_name: Supabase Realtime 채널 이름.

    Methods:
        subscribe_ho_state: ho_state 모든 상태 변경 알림 구독.
        subscribe_line_fact: line_fact 변경 알림 구독 (새 라인 학습).
        unsubscribe: 구독 해제 (채널명 일치 시).
        handle_event: 이벤트 수신 → 일치 콜백 호출 (테스트용 mock 메서드).
    """

    # 구독 금지 테이블 — 대량 insert 노이즈 방지
    FORBIDDEN_TABLES: frozenset[str] = frozenset({"evidence_log"})

    def __init__(self, channel_name: str) -> None:
        self._channel_name: str = channel_name
        # { callback: (schema, table) }
        self._subscriptions: dict[Callable[..., Any], tuple[str, str]] = {}
        # supabase-py RealtimeChannel (실제 연결 시 설정)
        self._channel: Any = None

    def subscribe_ho_state(self, callback: Callable[..., Any]) -> None:
        """ho_state 모든 상태 변경 알림 구독.

        등록만 수행. handle_event() 가 이벤트를 라우팅한다.

        Args:
            callback: 이벤트 수신 시 호출할 콜백 (event: dict) -> None.
        """
        self._subscriptions[callback] = ("public", "ho_state")

    def subscribe_line_fact(self, callback: Callable[..., Any]) -> None:
        """line_fact 변경 알림 구독 (새 라인 학습).

        Args:
            callback: 이벤트 수신 시 호출할 콜백 (event: dict) -> None.
        """
        self._subscriptions[callback] = ("public", "line_fact")

    def unsubscribe(self, channel_name: str) -> None:
        """구독 해제.

        channel_name 이 __init__ 생성자에 전달된 이름과 일치하면
        모든 구독을 해제한다. 일치하지 않으면 아무 일도 하지 않는다.

        Args:
            channel_name: 해제할 채널 이름.
        """
        if channel_name == self._channel_name:
            self._subscriptions.clear()
            self._channel = None

    def handle_event(self, event: dict[str, Any]) -> list[str]:
        """이벤트 수신 → 일치하는 콜백 호출.

        event["table"] 을 기준으로 구독 등록부에서 일치하는
        콜백을 모두 호출한다. 호출된 콜백의 __name__ 리스트를 반환한다.

        Args:
            event: Realtime 이벤트 딕셔너리.
                - "table": 변경된 테이블명 (필수).
                - "event_type": "INSERT"/"UPDATE"/"DELETE" (선택).
                - 기타 키는 callback 에 그대로 전달.

        Returns:
            호출된 콜백의 __name__ 리스트 (빈 리스트 가능).
        """
        table: str = event.get("table", "")

        # 구독 금지 테이블 — 대량 insert 무시
        if table in self.FORBIDDEN_TABLES:
            return []

        called: list[str] = []
        for callback, (_schema, sub_table) in list(self._subscriptions.items()):
            if sub_table == table:
                callback(event)
                cb_name: str = getattr(callback, "__name__", str(callback))
                called.append(cb_name)

        return called
