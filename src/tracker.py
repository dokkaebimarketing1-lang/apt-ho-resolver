"""호별 상태 추적 — 모든 상태 영구 저장, 데이터 삭제 금지.

HoState: 하나의 상태 관측 (frozen, 영구 보존).
Tracker: 상태 기록·조회·diff·공실 추론·미끼 탐지·유령 필터.

설계 원칙 (A43, A35, A30):
- 모든 상태(거주/매도/임대/공실/거래성사) 영구 저장. 삭제·TTL·파기 금지.
- 공실 = 음의 증거 → 매칭 시 후보에서 제외 (line_fact 적립용).
- 거래성사 → CLOSURE_LABEL 정답 라벨 생성.
- 미끼 의심도 HIGH → 적립/부스트 금지.
- 1회 관측으로 상태 확정 금지 (최소 N일 관측 필요).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional


# ============================================================
# Constants
# ============================================================

VALID_STATUSES: frozenset[str] = frozenset({
    "occupied",      # 거주
    "vacant",        # 공실
    "for_sale",      # 매도
    "for_rent",      # 임대
    "sold",          # 거래성사
})

STATUS_DISPLAY: dict[str, str] = {
    "occupied": "거주",
    "vacant": "공실",
    "for_sale": "매도",
    "for_rent": "임대",
    "sold": "거래성사",
}

# 미끼 매물 의심 임계 (일)
BAIT_LOW_DAYS = 90       # 3개월 이상 미판매 → LOW
BAIT_MID_DAYS = 180      # 6개월 이상 미판매 → MID
BAIT_HIGH_DAYS = 365     # 1년 이상 미판매 → HIGH


# ============================================================
# HoState — 하나의 상태 관측 (frozen, 영구 보존)
# ============================================================


@dataclass(frozen=True)
class HoState:
    """하나의 상태 관측 기록. frozen=True 로 불변.

    모든 관측은 영구 보존. 삭제·변경 금지.
    """
    complex_id: str
    canonical_ho_id: str
    status: str
    observed_at: datetime
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"알 수 없는 상태: {self.status!r}. "
                f"유효 상태: {sorted(VALID_STATUSES)}"
            )


# ============================================================
# Tracker — 상태 기록·조회·분석
# ============================================================


class Tracker:
    """호별 상태 추적기. 모든 데이터 영구 저장 (dict 기반, DB 없음).

    Methods:
        record_observation: 상태 관측 기록
        get_current_state: 최신 상태 조회
        get_state_history: 전체 이력
        detect_disappeared: 스냅샷 diff → 사라진 매물
        classify_vacancy: 공실 추론
        compute_bait_score: 미끼 매물 의심도
        filter_ghost_listings: 유령 매물 필터
    """

    def __init__(self) -> None:
        # { (complex_id, canonical_ho_id): [HoState, ...] }
        self._states: dict[tuple[str, str], list[HoState]] = {}

    # --------------------------------------------------
    # 기록 — 영구 저장, 삭제 금지
    # --------------------------------------------------

    def record_observation(
        self,
        complex_id: str,
        canonical_ho_id: str,
        status: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> HoState:
        """상태 관측 기록. 영구 저장 (삭제 없음).

        Args:
            complex_id: 단지 ID.
            canonical_ho_id: 정규화된 호 ID.
            status: 상태 (occupied/vacant/for_sale/for_rent/sold).
            source: 출처 채널명.
            metadata: 추가 메타데이터 (선택).

        Returns:
            생성된 HoState.

        Raises:
            ValueError: 알 수 없는 상태.
        """
        state = HoState(
            complex_id=complex_id,
            canonical_ho_id=canonical_ho_id,
            status=status,
            observed_at=datetime.now(),
            source=source,
            metadata=metadata or {},
        )
        key = (complex_id, canonical_ho_id)
        if key not in self._states:
            self._states[key] = []
        self._states[key].append(state)
        return state

    # --------------------------------------------------
    # 조회
    # --------------------------------------------------

    def get_current_state(
        self,
        complex_id: str,
        canonical_ho_id: str,
    ) -> HoState | None:
        """최신 상태 조회 (observed_at 기준).

        Args:
            complex_id: 단지 ID.
            canonical_ho_id: 정규화된 호 ID.

        Returns:
            최신 HoState 또는 None (관측 없음).
        """
        key = (complex_id, canonical_ho_id)
        history = self._states.get(key)
        if not history:
            return None
        return max(history, key=lambda s: s.observed_at)

    def get_state_history(
        self,
        complex_id: str,
        canonical_ho_id: str,
    ) -> list[HoState]:
        """전체 이력 반환 (영구, 시간순).

        모든 관측을 그대로 반환. 삭제·필터링 없음.

        Args:
            complex_id: 단지 ID.
            canonical_ho_id: 정규화된 호 ID.

        Returns:
            HoState 리스트 (observed_at 오름차순). 빈 리스트 가능.
        """
        key = (complex_id, canonical_ho_id)
        history = self._states.get(key, [])
        return sorted(history, key=lambda s: s.observed_at)

    # --------------------------------------------------
    # 스냅샷 diff — 사라진 매물 감지
    # --------------------------------------------------

    def detect_disappeared(
        self,
        current_listings: list[dict[str, Any]],
        previous_listings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """이전 스냅샷엔 있고 현재엔 없는 매물 감지.

        Args:
            current_listings: 현재 시점 매물 리스트.
            previous_listings: 이전 시점 매물 리스트.

        Returns:
            이전엔 있었으나 현재 사라진 매물 리스트.
        """
        def _key(l: dict[str, Any]) -> tuple[str, str]:
            return (str(l.get("complex_id", "")), str(l.get("ho_id", "")))

        current_keys: set[tuple[str, str]] = {_key(l) for l in current_listings}
        disappeared: list[dict[str, Any]] = []
        for listing in previous_listings:
            if _key(listing) not in current_keys:
                disappeared.append(listing)
        return disappeared

    # --------------------------------------------------
    # 공실 추론
    # --------------------------------------------------

    def classify_vacancy(
        self,
        unit_states: list[HoState],
    ) -> dict[str, str]:
        """호 상태 리스트를 분석하여 공실 추론.

        논리:
        - 거래(for_sale/for_rent) 0건 + 매물 0건 → "vacancy_candidate"
        - 거래(for_sale/for_rent) 1건 이상 → "active"
        - sold(거래성사) 1건 이상 → "transacted"
        - 그 외 → "unknown"

        공실 후보는 음의 증거 → 매칭 시 후보에서 제외.

        Args:
            unit_states: 특정 호의 전체 상태 이력.

        Returns:
            {"vacancy_status": str, "reason": str}
        """
        has_sale_or_rent = any(
            s.status in ("for_sale", "for_rent") for s in unit_states
        )
        has_sold = any(s.status == "sold" for s in unit_states)
        has_vacant = any(s.status == "vacant" for s in unit_states)
        has_occupied = any(s.status == "occupied" for s in unit_states)

        if has_sold:
            return {
                "vacancy_status": "transacted",
                "reason": "거래성사 기록 존재",
            }
        if has_sale_or_rent:
            return {
                "vacancy_status": "active",
                "reason": "매도/임대 활동 기록 존재",
            }
        if has_occupied:
            return {
                "vacancy_status": "active",
                "reason": "거주 기록 존재",
            }
        if has_vacant:
            return {
                "vacancy_status": "vacancy_candidate",
                "reason": "공실 기록만 존재 (음의 증거)",
            }
        return {
            "vacancy_status": "unknown",
            "reason": "관측 기록 없음",
        }

    # --------------------------------------------------
    # 미끼 매물 의심도
    # --------------------------------------------------

    def compute_bait_score(self, listing: dict[str, Any]) -> str:
        """매물의 미끼 의심도 계산.

        규칙:
        - listing에 first_seen_at(최초등록일)이 없으면 "LOW" (정보 부족).
        - 경과 일수 < 90일 → "LOW"
        - 90일 ≤ 경과일 < 180일 → "MID"
        - 180일 ≤ 경과일 < 365일 → "MID"
        - 365일 ≤ 경과일 → "HIGH" (적립/부스트 금지)

        Args:
            listing: 매물 dict (first_seen_at: datetime|str key 필요).

        Returns:
            "LOW" / "MID" / "HIGH"
        """
        first_seen = listing.get("first_seen_at")
        if first_seen is None:
            return "LOW"

        if isinstance(first_seen, str):
            try:
                first_seen_dt = datetime.fromisoformat(first_seen)
            except (ValueError, TypeError):
                return "LOW"
        elif isinstance(first_seen, datetime):
            first_seen_dt = first_seen
        else:
            return "LOW"

        elapsed_days = (datetime.now() - first_seen_dt).days
        if elapsed_days < BAIT_LOW_DAYS:
            return "LOW"
        if elapsed_days < BAIT_HIGH_DAYS:
            return "MID"
        return "HIGH"

    # --------------------------------------------------
    # 유령 매물 필터
    # --------------------------------------------------

    def filter_ghost_listings(
        self,
        listings: list[dict[str, Any]],
        min_observations: int = 2,
    ) -> list[dict[str, Any]]:
        """유령 매물 필터 — N회 이상 관측된 매물만 반환.

        동일 (complex_id, ho_id)가 최소 min_observations회 이상
        서로 다른 시점의 스냅샷에 등장한 경우만 유효 매물로 간주.

        Args:
            listings: 전체 매물 리스트.
            min_observations: 최소 관측 횟수 (기본 2).

        Returns:
            유효 매물 리스트 (최소 N회 이상 관측).
        """
        from collections import Counter

        key_counts: Counter[tuple[str, str]] = Counter()
        for listing in listings:
            key = (
                str(listing.get("complex_id", "")),
                str(listing.get("ho_id", "")),
            )
            key_counts[key] += 1

        result: list[dict[str, Any]] = []
        for listing in listings:
            key = (
                str(listing.get("complex_id", "")),
                str(listing.get("ho_id", "")),
            )
            if key_counts[key] >= min_observations:
                result.append(listing)
        return result
