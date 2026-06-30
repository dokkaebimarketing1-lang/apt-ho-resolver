"""도메인 모델 — Listing/Evidence/HoConclusion/Provenance + 유틸리티 함수.

설계 원칙:
- 모든 호 결론은 추정(is_estimate=True)이 기본. 정답 라벨만 예외.
- 모든 결론·증거에 출처추적(provenance) + 신뢰도(confidence)를 단다.
- Pillar는 현행 플랜(Fellegi-Sunter 중심) 4종으로 재정의.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Pillar(str, Enum):
    """증거 기둥 — 어느 추론 단계에서 생성된 증거인가."""
    UNIT_RESOLUTION = "unit_resolution"  # 호 식별 (전용면적 역추론)
    HO_COMPLETION = "ho_completion"      # 호 완성 (인접 증거 융합)
    CLOSURE_LABEL = "closure_label"      # 정답 라벨 (실거래 확정)
    LEDGER = "ledger"                    # 대장 (공공데이터 원천)


class FloorKind(str, Enum):
    """층 종류 — 정확층·저층·중층·고층."""
    EXACT = "exact"
    LOW = "low"
    MID = "mid"
    HIGH = "high"


class TradeType(str, Enum):
    """거래 유형."""
    SALE = "sale"        # 매매
    JEONSE = "jeonse"    # 전세
    WOLSE = "wolse"      # 월세


@dataclass(frozen=True)
class Provenance:
    """출처추적 — 어느 채널·게시물에서 왔는가.

    is_public 은 항상 True 여야 한다(합법선).
    비공개 출처(is_public=False)로 생성하면 ValueError.
    """
    channel: str
    source_id: str
    url: str
    captured_at: datetime
    is_public: bool = True

    def __post_init__(self) -> None:
        if not self.is_public:
            raise ValueError(
                "비공개 출처는 금지된다(합법선). is_public=True 만 허용."
            )


@dataclass(frozen=True)
class Evidence:
    """하나의 단서 — 어떤 필드를 어떤 값으로, 어느 기둥/출처에서, 얼마나 확신하는가."""
    field: str
    value: Any
    pillar: Pillar
    provenance: Provenance
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence 는 0.0~1.0 이어야 합니다: {self.confidence}"
            )


@dataclass
class Listing:
    """한 채널의 단일 매물(일부 필드 흐림 가능).

    채널마다 흐리는 필드가 다름. Fellegi-Sunter 융합이 같은 세대의
    여러 Listing 을 묶어 합집합한다.
    """
    complex_id: str
    dong: str
    floor_info: str
    floor_kind: FloorKind
    area2: float
    direction: str
    trade_type: TradeType
    price_manwon: int
    ho_hint: Optional[str] = None
    provenance: Optional[Provenance] = None


@dataclass
class HoConclusion:
    """최종 호 결론 — 후보·등급·출처체인. is_estimate 가 기본 True."""
    complex_id: str
    dong: str
    candidate_hos: list[dict[str, Any]] = field(default_factory=list)
    ho_final: Optional[str] = None
    grade: str = "none"
    is_estimate: bool = True
    evidence: list[Evidence] = field(default_factory=list)
    method_log: list[str] = field(default_factory=list)


_DIRECTION_MAP: dict[str, str] = {
    "남향": "S",
    "북향": "N",
    "동향": "E",
    "서향": "W",
    "남동향": "SE",
    "남서향": "SW",
    "북동향": "NE",
    "북서향": "NW",
}


def normalize_direction(raw: str) -> str:
    """한글 방향 표기를 영문 코드로 정규화.

    Args:
        raw: 한글 방향 문자열 (예: "남향", "남동향").

    Returns:
        영문 방향 코드 ("S", "SE" 등).

    Raises:
        ValueError: 알 수 없는 방향 문자열.
    """
    result = _DIRECTION_MAP.get(raw)
    if result is None:
        raise ValueError(f"알 수 없는 방향: {raw!r}")
    return result


def parse_floor(raw: str) -> tuple[FloorKind, Optional[int]]:
    """층 문자열을 파싱하여 (FloorKind, 층번호) 반환.

    Args:
        raw: 층 표기 문자열.
            - "23" → (EXACT, 23)
            - "저/23" → (LOW, 23)
            - "고/15" → (HIGH, 15)
            - "중" → (MID, None)

    Returns:
        (FloorKind, Optional[int]) 튜플.
    """
    raw = raw.strip()
    if "/" in raw:
        prefix, num_part = raw.split("/", 1)
        prefix = prefix.strip()
        num_part = num_part.strip()
    else:
        prefix = raw
        num_part = ""

    if prefix == "저":
        kind = FloorKind.LOW
    elif prefix == "중":
        return (FloorKind.MID, None)
    elif prefix == "고":
        kind = FloorKind.HIGH
    else:
        kind = FloorKind.EXACT
        num_part = raw

    if num_part:
        try:
            return (kind, int(num_part))
        except ValueError:
            pass
    return (kind, None)
