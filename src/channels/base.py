"""ChannelCollector Protocol + BaseChannel 추상 기반 클래스.

설계 의도:
- ChannelCollector: 모든 채널 수집기가 만족해야 하는 인터페이스 (Protocol)
- BaseChannel: 재시도·백오프·폴백을 구현하는 ABC

사용법:
    class MyChannel(BaseChannel):
        channel_name = "my_channel"
        reliability = 0.8

        def _do_collect(self, query: dict) -> list[dict]:
            resp = self._client.get(...)
            resp.raise_for_status()
            return resp.json()["data"]
"""

from __future__ import annotations

import abc
import time
from typing import Any, Protocol, runtime_checkable

import httpx


@runtime_checkable
class ChannelCollector(Protocol):
    """채널 수집기 인터페이스 (Protocol).

    모든 채널은 이 Protocol 을 만족해야 한다.
    BaseChannel 을 상속받으면 자연스럽게 만족한다.
    """
    channel_name: str
    reliability: float

    def collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """주어진 query 조건으로 채널 데이터를 수집한다.

        Args:
            query: 검색 조건 dict (키는 채널마다 다름).

        Returns:
            수집된 raw 데이터 리스트. 실패 시 빈 리스트.
        """
        ...


class BaseChannel(abc.ABC):
    """추상 기반 채널 — 재시도·지수 백오프·폴백 공통 구현."""

    channel_name: str = ""
    reliability: float = 0.0

    def __init__(self, api_key: str | None = None,
                 client: httpx.Client | None = None) -> None:
        """BaseChannel 생성자.

        Args:
            api_key: API 인증 키. None 이면 PUBLIC_DATA_API_KEY 환경변수 사용.
            client: httpx.Client. None 이면 기본 타임아웃(30초)으로 생성.
        """
        import os

        self._api_key = api_key or os.environ.get("PUBLIC_DATA_API_KEY", "")
        self._client = client or httpx.Client(timeout=30.0)

    @abc.abstractmethod
    def _do_collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """실제 API 호출 — 서브클래스가 구현한다.

        Args:
            query: 검색 조건 dict.

        Returns:
            수집된 raw 데이터 리스트.

        Raises:
            httpx.TimeoutException: 타임아웃.
            httpx.HTTPStatusError: HTTP 에러 (4xx/5xx).
            httpx.ConnectError: 연결 실패.
        """
        ...

    def collect(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """재시도·백오프·폴백 래퍼.

        - 복구 가능 에러(Timeout / HTTPStatus / Connect): 최대 3회 재시도.
        - 재시도 간격: 지수 백오프 (1s, 2s, 4s).
        - 복구 불가 에러: 즉시 폴백(빈 리스트).
        - 최종 실패: 빈 리스트 반환 (호출자에게 예외 전파 안 함).

        Args:
            query: 검색 조건 dict (그대로 _do_collect 로 전달).

        Returns:
            수집된 데이터 리스트. 모든 시도 실패 시 빈 리스트.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return self._do_collect(query)
            except (httpx.TimeoutException,
                    httpx.HTTPStatusError,
                    httpx.ConnectError) as exc:
                if attempt == max_retries - 1:
                    return []
                time.sleep(2 ** attempt)
            except Exception:
                return []
        return []  # unreachable but satisfies return type
