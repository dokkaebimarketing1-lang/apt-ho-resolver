"""LH 청약플러스 공실정보지도 채널.

apply.lh.or.kr 에서 LH 임대 단지의 공실 정보를 수집한다.
LH 임대 단지만 처리하며, 비임대 단지는 collect() 가 None 을 반환한다.

channel_name = 'lh_vacancy'
reliability = 0.9  (LH 공사 직접 제공이므로 높은 신뢰도)

References:
    A45 (LH 공실 VERIFIED) — apply.lh.or.kr 주간 업데이트 공실정보지도.
    A43 (호별 상태 추적) — 공실 = 음의 증거로 후보 제소.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

import httpx


__all__ = [
    "ChannelCollector",
    "LhVacancyData",
    "LhVacancyChannel",
    "is_lh_rental_complex",
]


# ---------------------------------------------------------------------------
# 채널 수집기 프로토콜 (임시 — src/channels/base.py 가 Todo 11 에서 작성되면 대체)
# ---------------------------------------------------------------------------


@runtime_checkable
class ChannelCollector(Protocol):
    """채널 수집기의 기본 프로토콜.

    모든 채널(channel) 은 이 프로토콜을 구현해야 한다.
    Todo 11(src/channels/base.py)에서 정식 ABC/Protocol 로 대체 예정.
    """

    channel_name: str
    reliability: float

    def collect(self, **kwargs) -> list:  # pragma: no cover
        ...


# ---------------------------------------------------------------------------
# 도메인 데이터 클래스
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LhVacancyData:
    """LH 임대 단지 공실 정보.

    Attributes:
        complex_id:   단지 식별자 (예: "LH-2026-001").
        complex_name: 단지명 (예: "LH 행복타운 1단지").
        region:       지역 (시/도, 예: "서울특별시").
        total_units:  전체 세대 수.
        vacant_units: 공실 세대 수.
        is_lh_rental: LH 임대 단지 여부 (항상 True).
        collected_at: 수집 시각.
    """

    complex_id: str
    complex_name: str
    region: str
    total_units: int
    vacant_units: int
    is_lh_rental: bool = True
    collected_at: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# LH 임대 단지 판별
# ---------------------------------------------------------------------------


_LH_RENTAL_KEYWORDS: list[str] = [
    "행복주택",
    "국민임대",
    "영구임대",
    "공공임대",
    "전세임대",
    "매입임대",
    "통합공공임대",
    "희망타운",
    "LH임대",
    "엘에이치임대",
]


def is_lh_rental_complex(complex_name: str) -> bool:
    """단지명으로 LH 임대 단지인지 판별한다.

    LH 비임대 단지에 공실 정보가 적용되는 것을 방지하기 위한 필터.

    Args:
        complex_name: 단지명 (예: "LH 행복타운 1단지").

    Returns:
        LH 임대 단지이면 True, 아니면 False.
    """
    name = complex_name.strip()
    if not name:
        return False

    name_upper = name.upper()

    # "LH" 또는 "엘에이치" 로 시작하면 LH 단지
    if name_upper.startswith("LH") or name_upper.startswith("엘에이치"):
        return True

    # 키워드 포함 여부 검사
    for kw in _LH_RENTAL_KEYWORDS:
        if kw in name:
            return True

    return False


# ---------------------------------------------------------------------------
# LH 공실정보 채널
# ---------------------------------------------------------------------------


class LhVacancyChannel:
    """LH 청약플러스 공실정보지도 채널.

    apply.lh.or.kr 의 공실정보 API 를 통해 LH 임대 단지의
    전체 세대 수 및 공실 세대 수를 수집한다.

    Attributes:
        channel_name: 'lh_vacancy' (고정).
        reliability:  0.9 (LH 공사 직접 제공 — 신뢰도 높음).
    """

    channel_name: str = "lh_vacancy"
    reliability: float = 0.9

    # LH 공실정보지도 API 엔드포인트
    BASE_URL = "https://apply.lh.or.kr"
    VACANCY_API_PATH = "/api/v1/vacancy"

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        """LhVacancyChannel 생성자.

        Args:
            client: 주입 가능한 httpx.Client (테스트용 Mock).
                    None 이면 기본 클라이언트를 지연 생성한다.
        """
        self._client = client

    def _get_client(self) -> httpx.Client:
        """내부 HTTP 클라이언트를 반환한다 (지연 생성).

        Returns:
            httpx.Client 인스턴스.
        """
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.BASE_URL,
                timeout=30.0,
            )
        return self._client

    def collect(
        self,
        complex_id: str,
        complex_name: str,
        region: str,
    ) -> Optional[LhVacancyData]:
        """지정 단지의 LH 공실 정보를 수집한다.

        Args:
            complex_id:   단지 식별자.
            complex_name: 단지명.
            region:       지역 (시/도).

        Returns:
            LH 임대 단지인 경우 LhVacancyData,
            비LH 단지이거나 API 호출 실패 시 None.
        """
        # ── 1. LH 임대 단지 필터링 ──────────────────────────────────
        if not is_lh_rental_complex(complex_name):
            return None

        # ── 2. API 호출 ─────────────────────────────────────────────
        client = self._get_client()
        try:
            response = client.get(
                self.VACANCY_API_PATH,
                params={
                    "complexId": complex_id,
                    "region": region,
                },
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError, KeyError):
            return None

        # ── 3. 응답 파싱 ────────────────────────────────────────────
        try:
            return LhVacancyData(
                complex_id=complex_id,
                complex_name=complex_name,
                region=region,
                total_units=int(data["totalUnits"]),
                vacant_units=int(data["vacantUnits"]),
                is_lh_rental=True,
                collected_at=datetime.now(),
            )
        except (KeyError, ValueError, TypeError):
            return None

    def collect_by_region(self, region: str) -> list[LhVacancyData]:
        """지역별 LH 임대 단지 공실 정보를 수집한다.

        Args:
            region: 지역 (시/도, 예: "서울특별시").

        Returns:
            해당 지역 LH 임대 단지들의 공실 정보 목록.
            API 실패 시 빈 리스트.
        """
        client = self._get_client()
        try:
            response = client.get(
                self.VACANCY_API_PATH,
                params={"region": region},
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError, KeyError):
            return []

        # 리스트 응답과 단일 응답 모두 처리
        items: list = data if isinstance(data, list) else [data]

        results: list[LhVacancyData] = []
        for item in items:
            try:
                results.append(
                    LhVacancyData(
                        complex_id=str(item["complexId"]),
                        complex_name=str(item["complexName"]),
                        region=region,
                        total_units=int(item["totalUnits"]),
                        vacant_units=int(item["vacantUnits"]),
                        is_lh_rental=True,
                        collected_at=datetime.now(),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue

        return results
