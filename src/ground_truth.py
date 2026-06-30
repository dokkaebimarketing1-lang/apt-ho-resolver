"""GroundTruth — 정답 라벨 다원화 + RTMS⋈등기 조인 (A3, A85).

설계 원칙:
- GroundTruth base: 모든 subtype이 (동, 층, 면적, 호, 향, 신뢰도, 출처) 제공.
- is_ground_truth() -> CLOSURE_LABEL 소스만 True.
- RtmsRegistryJoin: RTMS 단독 라벨 불가 - 등기 조인 후 True (A85).
- 2대 라벨원: RtmsRegistryJoin + AuctionResult.
- to_evidence() -> Evidence 변환 (pillar = CLOSURE_LABEL or LEDGER).

References:
    A3  — 정답 라벨 다원화 (4원: RTMS⋈등기, 경매, 등기확인, LH공실).
    A85 — RTMS 단독 라벨 불가. 반드시 등기 조인 후 라벨화.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain import Evidence, Pillar, Provenance

__all__ = [
    "GroundTruth",
    "RtmsRegistryJoin",
    "AuctionResult",
    "RegistryConfirm",
    "LhVacancy",
]


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroundTruth:
    """정답 라벨 base - subtype이 (동, 층, 면적, 호, 향, 신뢰도, 출처) 제공.

    is_ground_truth() -> CLOSURE_LABEL 소스만 True (기본 False).
    to_evidence()     -> Evidence 변환.

    Subtype은 다음 속성을 제공해야 한다 (duck typing):
        dong       : str          - 동 번호.
        floor      : int | None   - 층.
        area_m2    : float | None - 전용면적.
        ho         : str | None   - 호 번호.
        direction  : str | None   - 향 (영문 코드).
        confidence : float        - 신뢰도 (0.0~1.0).
        source     : str          - 출처 식별자.
    """

    def is_ground_truth(self) -> bool:
        """CLOSURE_LABEL 소스만 True. 기본 False, subtype이 override."""
        return False

    def to_evidence(self, provenance: Provenance) -> Evidence:
        """GroundTruth -> Evidence 변환.

        is_ground_truth()=True  -> Pillar.CLOSURE_LABEL.
        is_ground_truth()=False -> Pillar.LEDGER.

        Args:
            provenance: 출처 정보.

        Returns:
            Evidence (field="ho", value=self.ho).
        """
        pillar = (
            Pillar.CLOSURE_LABEL
            if self.is_ground_truth()
            else Pillar.LEDGER
        )
        return Evidence(
            field="ho",
            value=self.ho,  # type: ignore[attr-defined]
            pillar=pillar,
            provenance=provenance,
            confidence=self.confidence,  # type: ignore[attr-defined]
        )


# ---------------------------------------------------------------------------
# Subtype 1: RtmsRegistryJoin (A85)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RtmsRegistryJoin(GroundTruth):
    """RTMS 행(금액+날짜+면적+층)과 집합건물 등기 호의 조인 결과 (A85).

    RTMS 단독 라벨 불가 - registry_ho 가 None 이면 is_ground_truth()=False.
    등기 조인 후(registry_ho 설정) is_ground_truth()=True.

    Attributes:
        complex_id:    단지 식별자.
        rtms_dong:     RTMS 동 (예: "101동").
        floor:         층.
        area_m2:       전용면적(m2).
        price_manwon:  거래금액(만원).
        contract_date: 계약일 "YYYY-MM-DD".
        direction:     향 (영문 코드, RTMS에 없음 - 보통 None).
        registry_dong: 등기 동 (조인 전 None).
        registry_ho:   등기 호 (조인 전 None - 이 값이 있어야 라벨).
    """

    complex_id: str
    rtms_dong: str
    floor: int
    area_m2: float
    price_manwon: int
    contract_date: str
    direction: str | None = None
    registry_dong: str | None = None
    registry_ho: str | None = None

    @property
    def dong(self) -> str:
        """동 - 등기 동 우선, 없으면 RTMS 동."""
        return self.registry_dong or self.rtms_dong

    @property
    def ho(self) -> str | None:
        """호 - 등기 호 (조인 전 None)."""
        return self.registry_ho

    @property
    def confidence(self) -> float:
        """신뢰도 - 등기 조인 시 0.95, 미조인 시 0.0."""
        return 0.95 if self.registry_ho is not None else 0.0

    @property
    def source(self) -> str:
        return "rtms_registry_join"

    def is_ground_truth(self) -> bool:
        """등기 조인 후(registry_ho 설정) True. RTMS 단독 False (A85)."""
        return self.registry_ho is not None


# ---------------------------------------------------------------------------
# Subtype 2: AuctionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuctionResult(GroundTruth):
    """법원경매 결과 - 동, 호, 층, 면적, 향, 감정가.

    경매 동·호는 100% 공개이므로 CLOSURE_LABEL 정답 라벨.

    Attributes:
        complex_id:           단지 식별자.
        dong:                 동 (예: "101동").
        ho:                   호 (예: "1503").
        floor:                층 (None 가능).
        area_m2:              전용면적(m2) (None 가능).
        direction:            향 영문 코드 (None 가능).
        appraised_price_won:  감정가(원) (None 가능).
        case_no:              사건번호.
    """

    complex_id: str
    dong: str
    ho: str
    floor: int | None = None
    area_m2: float | None = None
    direction: str | None = None
    appraised_price_won: int | None = None
    case_no: str = ""

    @property
    def confidence(self) -> float:
        return 0.95

    @property
    def source(self) -> str:
        return "auction"

    def is_ground_truth(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Subtype 3: RegistryConfirm
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryConfirm(GroundTruth):
    """등기부 확인 - 동, 호, 소유자주소.

    등기부는 법적 효력이 있으므로 CLOSURE_LABEL 정답 라벨.
    단, 층·면적·향 정보는 등기부에 없다.

    Attributes:
        complex_id:     단지 식별자.
        dong:           동 (예: "101").
        ho:             호 (예: "1503").
        owner_address:  소유자 주소 (미거주 신호용).
        is_non_resident: 소유자 미거주 추정 여부.
    """

    complex_id: str
    dong: str
    ho: str
    owner_address: str = ""
    is_non_resident: bool = False

    @property
    def floor(self) -> int | None:
        return None

    @property
    def area_m2(self) -> float | None:
        return None

    @property
    def direction(self) -> str | None:
        return None

    @property
    def confidence(self) -> float:
        return 0.98

    @property
    def source(self) -> str:
        return "registry"

    def is_ground_truth(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Subtype 4: LhVacancy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LhVacancy(GroundTruth):
    """LH 공실 정보 - 단지 수준 공실 (호별 아님).

    공실 = 음의 증거. 정답 라벨이 아니다 (is_ground_truth()=False).

    Attributes:
        complex_id:   단지 식별자.
        complex_name: 단지명.
        region:       지역 (시/도).
        total_units:  전체 세대 수.
        vacant_units: 공실 세대 수.
    """

    complex_id: str
    complex_name: str
    region: str
    total_units: int
    vacant_units: int

    @property
    def dong(self) -> str:
        return ""

    @property
    def ho(self) -> str | None:
        return None

    @property
    def floor(self) -> int | None:
        return None

    @property
    def area_m2(self) -> float | None:
        return None

    @property
    def direction(self) -> str | None:
        return None

    @property
    def confidence(self) -> float:
        return 0.9

    @property
    def source(self) -> str:
        return "lh_vacancy"

    def is_ground_truth(self) -> bool:
        return False
