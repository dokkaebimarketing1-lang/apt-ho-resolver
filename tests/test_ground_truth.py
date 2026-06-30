"""GroundTruth + 4 subtypes 단위 테스트.

테스트 전략:
- 각 subtype 생성 + 속성 (동, 층, 면적, 호, 향, 신뢰도, 출처) 검증.
- is_ground_truth() 판정: CLOSURE_LABEL 소스만 True.
- RtmsRegistryJoin 호 부착: RTMS 단독 -> False, 등기 조인 후 -> True (A85).
- to_evidence() 변환: pillar = CLOSURE_LABEL or LEDGER.
- frozen=True 검증.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain import Evidence, Pillar, Provenance
from src.ground_truth import (
    AuctionResult,
    GroundTruth,
    LhVacancy,
    RegistryConfirm,
    RtmsRegistryJoin,
)


# ============================================================
# Helpers
# ============================================================


def _make_provenance(channel: str = "test") -> Provenance:
    """테스트용 Provenance 생성."""
    return Provenance(
        channel=channel,
        source_id="src-001",
        url="https://example.com/test",
        captured_at=datetime(2026, 6, 29, 12, 0, 0),
    )


# ============================================================
# Test: GroundTruth base
# ============================================================


class TestGroundTruthBase:
    """GroundTruth base dataclass 기본 동작."""

    def test_is_dataclass(self) -> None:
        """Given GroundTruth class Then frozen dataclass."""
        import dataclasses
        assert dataclasses.is_dataclass(GroundTruth)

    def test_base_is_ground_truth_false(self) -> None:
        """Given GroundTruth base Then is_ground_truth()=False (기본)."""
        gt = GroundTruth()
        assert gt.is_ground_truth() is False

    def test_frozen(self) -> None:
        """Given GroundTruth instance When 속성 설정 Then FrozenInstanceError."""
        gt = GroundTruth()
        with pytest.raises(AttributeError):
            gt.foo = 1  # type: ignore[attr-defined]

    def test_to_evidence_uses_is_ground_truth(self) -> None:
        """Given GroundTruth subclass When to_evidence Then pillar 결정."""
        # is_ground_truth()=False -> LEDGER
        gt: GroundTruth = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        ev = gt.to_evidence(_make_provenance("lh"))
        assert ev.pillar == Pillar.LEDGER
        assert ev.field == "ho"


# ============================================================
# Test: RtmsRegistryJoin
# ============================================================


class TestRtmsRegistryJoin:
    """RtmsRegistryJoin — RTMS ⋈ 등기 조인 (A85)."""

    def test_rtms_alone_not_ground_truth(self) -> None:
        """Given RTMS 단독 (registry_ho=None) Then is_ground_truth()=False (A85)."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        assert gt.registry_ho is None
        assert gt.is_ground_truth() is False

    def test_rtms_joined_is_ground_truth(self) -> None:
        """Given RTMS + 등기 조인 (registry_ho 설정) Then is_ground_truth()=True."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_dong="101",
            registry_ho="1503",
        )
        assert gt.is_ground_truth() is True

    def test_ho_attached_after_join(self) -> None:
        """Given 등기 조인 후 When ho 접근 Then registry_ho 반환 (호 부착)."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        assert gt.ho == "1503"

    def test_ho_none_before_join(self) -> None:
        """Given RTMS 단독 When ho 접근 Then None (호 미부착)."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        assert gt.ho is None

    def test_dong_registry_preferred(self) -> None:
        """Given 등기 동 + RTMS 동 When dong 접근 Then 등기 동 우선."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_dong="101",
            registry_ho="1503",
        )
        assert gt.dong == "101"

    def test_dong_rtms_fallback(self) -> None:
        """Given 등기 동 None When dong 접근 Then RTMS 동 fallback."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        assert gt.dong == "101동"

    def test_confidence_joined(self) -> None:
        """Given 등기 조인 후 Then confidence=0.95."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        assert gt.confidence == 0.95

    def test_confidence_not_joined(self) -> None:
        """Given RTMS 단독 Then confidence=0.0."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        assert gt.confidence == 0.0

    def test_source(self) -> None:
        """Given RtmsRegistryJoin Then source='rtms_registry_join'."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        assert gt.source == "rtms_registry_join"

    def test_all_fields_provided(self) -> None:
        """Given RtmsRegistryJoin Then (동, 층, 면적, 호, 향, 신뢰도, 출처) 제공."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            direction="S",
            registry_dong="101",
            registry_ho="1503",
        )
        assert gt.dong == "101"
        assert gt.floor == 15
        assert gt.area_m2 == 84.12
        assert gt.ho == "1503"
        assert gt.direction == "S"
        assert gt.confidence == 0.95
        assert gt.source == "rtms_registry_join"

    def test_rtms_fields_preserved(self) -> None:
        """Given 등기 조인 후에도 RTMS 필드 보존."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        assert gt.rtms_dong == "101동"
        assert gt.price_manwon == 100000
        assert gt.contract_date == "2026-06-29"

    def test_frozen(self) -> None:
        """Given RtmsRegistryJoin When 속성 설정 Then FrozenInstanceError."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        with pytest.raises(AttributeError):
            gt.floor = 20  # type: ignore[misc]

    def test_to_evidence_joined(self) -> None:
        """Given 등기 조인 후 When to_evidence Then CLOSURE_LABEL."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        prov = _make_provenance("rtms_registry")
        ev = gt.to_evidence(prov)
        assert ev.field == "ho"
        assert ev.value == "1503"
        assert ev.pillar == Pillar.CLOSURE_LABEL
        assert ev.confidence == 0.95
        assert ev.provenance == prov

    def test_to_evidence_not_joined(self) -> None:
        """Given RTMS 단독 When to_evidence Then LEDGER + value=None."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        ev = gt.to_evidence(_make_provenance("rtms"))
        assert ev.pillar == Pillar.LEDGER
        assert ev.value is None
        assert ev.confidence == 0.0

    def test_partial_join_ho_only(self) -> None:
        """Given registry_ho만 있고 registry_dong은 None Then is_ground_truth()=True."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        assert gt.is_ground_truth() is True
        assert gt.dong == "101동"  # RTMS 동 fallback


# ============================================================
# Test: AuctionResult
# ============================================================


class TestAuctionResult:
    """AuctionResult — 법원경매 결과 (100% 공개)."""

    def test_is_ground_truth(self) -> None:
        """Given AuctionResult Then is_ground_truth()=True."""
        gt = AuctionResult(
            complex_id="C1",
            dong="101동",
            ho="1503",
        )
        assert gt.is_ground_truth() is True

    def test_full_fields(self) -> None:
        """Given 모든 필드 When 생성 Then 모든 속성 제공."""
        gt = AuctionResult(
            complex_id="C1",
            dong="101동",
            ho="1503",
            floor=15,
            area_m2=84.12,
            direction="S",
            appraised_price_won=500_000_000,
            case_no="2026타경12345",
        )
        assert gt.dong == "101동"
        assert gt.ho == "1503"
        assert gt.floor == 15
        assert gt.area_m2 == 84.12
        assert gt.direction == "S"
        assert gt.appraised_price_won == 500_000_000
        assert gt.case_no == "2026타경12345"

    def test_minimal_fields(self) -> None:
        """Given 최소 필드(동, 호만) When 생성 Then 옵션 필드 None."""
        gt = AuctionResult(
            complex_id="C1",
            dong="101동",
            ho="1503",
        )
        assert gt.floor is None
        assert gt.area_m2 is None
        assert gt.direction is None
        assert gt.appraised_price_won is None
        assert gt.case_no == ""

    def test_confidence(self) -> None:
        """Given AuctionResult Then confidence=0.95."""
        gt = AuctionResult(complex_id="C1", dong="101", ho="1503")
        assert gt.confidence == 0.95

    def test_source(self) -> None:
        """Given AuctionResult Then source='auction'."""
        gt = AuctionResult(complex_id="C1", dong="101", ho="1503")
        assert gt.source == "auction"

    def test_frozen(self) -> None:
        """Given AuctionResult When 속성 설정 Then FrozenInstanceError."""
        gt = AuctionResult(complex_id="C1", dong="101", ho="1503")
        with pytest.raises(AttributeError):
            gt.ho = "9999"  # type: ignore[misc]

    def test_to_evidence(self) -> None:
        """Given AuctionResult When to_evidence Then CLOSURE_LABEL."""
        gt = AuctionResult(
            complex_id="C1",
            dong="101동",
            ho="1503",
            floor=15,
            area_m2=84.12,
        )
        prov = _make_provenance("auction")
        ev = gt.to_evidence(prov)
        assert ev.field == "ho"
        assert ev.value == "1503"
        assert ev.pillar == Pillar.CLOSURE_LABEL
        assert ev.confidence == 0.95
        assert ev.provenance == prov

    def test_is_ground_truth_label_source(self) -> None:
        """Given AuctionResult Then 정답 라벨 소스 (2대 라벨원 중 하나)."""
        gt = AuctionResult(complex_id="C1", dong="101", ho="1503")
        assert gt.is_ground_truth() is True
        assert gt.source == "auction"


# ============================================================
# Test: RegistryConfirm
# ============================================================


class TestRegistryConfirm:
    """RegistryConfirm — 등기부 확인 (법적 효력)."""

    def test_is_ground_truth(self) -> None:
        """Given RegistryConfirm Then is_ground_truth()=True."""
        gt = RegistryConfirm(
            complex_id="C1",
            dong="101",
            ho="1503",
        )
        assert gt.is_ground_truth() is True

    def test_full_fields(self) -> None:
        """Given 모든 필드 When 생성 Then 속성 제공."""
        gt = RegistryConfirm(
            complex_id="C1",
            dong="101",
            ho="1503",
            owner_address="서울특별시 강남구 역삼동 123",
            is_non_resident=True,
        )
        assert gt.dong == "101"
        assert gt.ho == "1503"
        assert gt.owner_address == "서울특별시 강남구 역삼동 123"
        assert gt.is_non_resident is True

    def test_no_floor_area_direction(self) -> None:
        """Given RegistryConfirm Then 층/면적/향 = None (등기부에 없음)."""
        gt = RegistryConfirm(complex_id="C1", dong="101", ho="1503")
        assert gt.floor is None
        assert gt.area_m2 is None
        assert gt.direction is None

    def test_confidence(self) -> None:
        """Given RegistryConfirm Then confidence=0.98 (법적 효력)."""
        gt = RegistryConfirm(complex_id="C1", dong="101", ho="1503")
        assert gt.confidence == 0.98

    def test_source(self) -> None:
        """Given RegistryConfirm Then source='registry'."""
        gt = RegistryConfirm(complex_id="C1", dong="101", ho="1503")
        assert gt.source == "registry"

    def test_frozen(self) -> None:
        """Given RegistryConfirm When 속성 설정 Then FrozenInstanceError."""
        gt = RegistryConfirm(complex_id="C1", dong="101", ho="1503")
        with pytest.raises(AttributeError):
            gt.ho = "9999"  # type: ignore[misc]

    def test_to_evidence(self) -> None:
        """Given RegistryConfirm When to_evidence Then CLOSURE_LABEL."""
        gt = RegistryConfirm(
            complex_id="C1",
            dong="101",
            ho="1503",
            owner_address="서울 강남구",
        )
        prov = _make_provenance("registry")
        ev = gt.to_evidence(prov)
        assert ev.field == "ho"
        assert ev.value == "1503"
        assert ev.pillar == Pillar.CLOSURE_LABEL
        assert ev.confidence == 0.98
        assert ev.provenance == prov

    def test_default_values(self) -> None:
        """Given 최소 필드 When 생성 Then 기본값."""
        gt = RegistryConfirm(complex_id="C1", dong="101", ho="1503")
        assert gt.owner_address == ""
        assert gt.is_non_resident is False


# ============================================================
# Test: LhVacancy
# ============================================================


class TestLhVacancy:
    """LhVacancy — LH 공실 정보 (음의 증거, 정답 라벨 아님)."""

    def test_not_ground_truth(self) -> None:
        """Given LhVacancy Then is_ground_truth()=False (공실 = 음의 증거)."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        assert gt.is_ground_truth() is False

    def test_fields(self) -> None:
        """Given LhVacancy When 생성 Then 단지 수준 필드 제공."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        assert gt.complex_id == "C1"
        assert gt.complex_name == "LH 행복주택"
        assert gt.region == "서울특별시"
        assert gt.total_units == 100
        assert gt.vacant_units == 5

    def test_no_unit_level_data(self) -> None:
        """Given LhVacancy Then 동/호/층/면적/향 = None/빈값 (단지 수준)."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        assert gt.dong == ""
        assert gt.ho is None
        assert gt.floor is None
        assert gt.area_m2 is None
        assert gt.direction is None

    def test_confidence(self) -> None:
        """Given LhVacancy Then confidence=0.9."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        assert gt.confidence == 0.9

    def test_source(self) -> None:
        """Given LhVacancy Then source='lh_vacancy'."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        assert gt.source == "lh_vacancy"

    def test_frozen(self) -> None:
        """Given LhVacancy When 속성 설정 Then FrozenInstanceError."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        with pytest.raises(AttributeError):
            gt.vacant_units = 10  # type: ignore[misc]

    def test_to_evidence_ledger(self) -> None:
        """Given LhVacancy When to_evidence Then LEDGER (정답 라벨 아님)."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        prov = _make_provenance("lh_vacancy")
        ev = gt.to_evidence(prov)
        assert ev.field == "ho"
        assert ev.value is None
        assert ev.pillar == Pillar.LEDGER
        assert ev.confidence == 0.9
        assert ev.provenance == prov


# ============================================================
# Test: A85 — RTMS 단독 라벨 불가
# ============================================================


class TestA85RtmsStandaloneLabel:
    """A85: RTMS 단독 라벨 불가 - 반드시 등기 조인 후 라벨화."""

    def test_rtms_alone_cannot_label(self) -> None:
        """Given RTMS 단독 Then is_ground_truth()=False (라벨 불가)."""
        rtms_only = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        assert not rtms_only.is_ground_truth()
        assert rtms_only.ho is None
        assert rtms_only.confidence == 0.0

    def test_rtms_with_registry_can_label(self) -> None:
        """Given RTMS + 등기 조인 Then is_ground_truth()=True (라벨 가능)."""
        joined = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_dong="101",
            registry_ho="1503",
        )
        assert joined.is_ground_truth()
        assert joined.ho == "1503"
        assert joined.confidence == 0.95

    def test_join_attaches_ho(self) -> None:
        """Given 등기 호 부착 Then RTMS 행에 호가 붙는다."""
        before = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        after = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        assert before.ho is None
        assert after.ho == "1503"
        assert before.is_ground_truth() is False
        assert after.is_ground_truth() is True

    def test_two_label_sources(self) -> None:
        """Given 2대 라벨원 (RtmsRegistryJoin + AuctionResult) Then 모두 True."""
        rtms_join = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        auction = AuctionResult(
            complex_id="C1",
            dong="101동",
            ho="1503",
        )
        assert rtms_join.is_ground_truth()
        assert auction.is_ground_truth()

    def test_non_label_sources_false(self) -> None:
        """Given 비라벨 소스 (LhVacancy, RTMS 단독) Then 모두 False."""
        lh = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울특별시",
            total_units=100,
            vacant_units=5,
        )
        rtms_only = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        assert not lh.is_ground_truth()
        assert not rtms_only.is_ground_truth()


# ============================================================
# Test: to_evidence (cross-subtype)
# ============================================================


class TestToEvidence:
    """to_evidence() — 모든 subtype의 Evidence 변환."""

    def test_auction_to_evidence(self) -> None:
        """Given AuctionResult When to_evidence Then CLOSURE_LABEL Evidence."""
        gt = AuctionResult(
            complex_id="C1", dong="101", ho="1503",
            floor=15, area_m2=84.0, direction="S",
        )
        prov = _make_provenance("auction")
        ev = gt.to_evidence(prov)
        assert isinstance(ev, Evidence)
        assert ev.pillar == Pillar.CLOSURE_LABEL
        assert ev.value == "1503"
        assert ev.confidence == 0.95

    def test_registry_to_evidence(self) -> None:
        """Given RegistryConfirm When to_evidence Then CLOSURE_LABEL Evidence."""
        gt = RegistryConfirm(complex_id="C1", dong="101", ho="1503")
        prov = _make_provenance("registry")
        ev = gt.to_evidence(prov)
        assert isinstance(ev, Evidence)
        assert ev.pillar == Pillar.CLOSURE_LABEL
        assert ev.value == "1503"
        assert ev.confidence == 0.98

    def test_rtms_joined_to_evidence(self) -> None:
        """Given RtmsRegistryJoin(조인) When to_evidence Then CLOSURE_LABEL."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
            registry_ho="1503",
        )
        ev = gt.to_evidence(_make_provenance("rtms"))
        assert ev.pillar == Pillar.CLOSURE_LABEL
        assert ev.value == "1503"

    def test_rtms_alone_to_evidence_ledger(self) -> None:
        """Given RtmsRegistryJoin(단독) When to_evidence Then LEDGER."""
        gt = RtmsRegistryJoin(
            complex_id="C1",
            rtms_dong="101동",
            floor=15,
            area_m2=84.12,
            price_manwon=100000,
            contract_date="2026-06-29",
        )
        ev = gt.to_evidence(_make_provenance("rtms"))
        assert ev.pillar == Pillar.LEDGER
        assert ev.value is None

    def test_lh_to_evidence_ledger(self) -> None:
        """Given LhVacancy When to_evidence Then LEDGER."""
        gt = LhVacancy(
            complex_id="C1",
            complex_name="LH 행복주택",
            region="서울",
            total_units=100,
            vacant_units=5,
        )
        ev = gt.to_evidence(_make_provenance("lh"))
        assert ev.pillar == Pillar.LEDGER
        assert ev.value is None

    def test_evidence_provenance_preserved(self) -> None:
        """Given Provenance When to_evidence Then Evidence.provenance 보존."""
        gt = AuctionResult(complex_id="C1", dong="101", ho="1503")
        prov = _make_provenance("test_channel")
        ev = gt.to_evidence(prov)
        assert ev.provenance is prov
        assert ev.provenance.channel == "test_channel"
