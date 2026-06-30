"""도메인 모델 단위 테스트."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain import (
    Evidence,
    FloorKind,
    HoConclusion,
    Listing,
    Pillar,
    Provenance,
    TradeType,
    normalize_direction,
    parse_floor,
)


class TestProvenance:
    """Provenance 생성 및 is_public 검증."""

    def test_create_valid(self) -> None:
        """Given 유효한 필드 When Provenance 생성 Then 정상 생성"""
        p = Provenance(
            channel="zigbang",
            source_id="12345",
            url="https://zigbang.kr/article/12345",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
            is_public=True,
        )
        assert p.channel == "zigbang"
        assert p.source_id == "12345"
        assert p.url == "https://zigbang.kr/article/12345"
        assert p.is_public is True

    def test_is_public_default_true(self) -> None:
        """Given is_public 미지정 When Provenance 생성 Then 기본 True"""
        p = Provenance(
            channel="naver",
            source_id="999",
            url="https://naver.com",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        assert p.is_public is True

    def test_is_public_false_raises(self) -> None:
        """Given is_public=False When Provenance 생성 Then ValueError"""
        with pytest.raises(ValueError, match="비공개 출처"):
            Provenance(
                channel="naver",
                source_id="999",
                url="https://naver.com",
                captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
                is_public=False,
            )


class TestEvidence:
    """Evidence 생성 및 confidence 검증."""

    def test_create_valid(self) -> None:
        """Given 유효한 필드 When Evidence 생성 Then 정상 생성"""
        prov = Provenance(
            channel="zigbang",
            source_id="123",
            url="https://zigbang.kr/123",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        ev = Evidence(
            field="ho",
            value="101",
            pillar=Pillar.UNIT_RESOLUTION,
            provenance=prov,
            confidence=0.85,
        )
        assert ev.field == "ho"
        assert ev.value == "101"
        assert ev.pillar == Pillar.UNIT_RESOLUTION
        assert ev.confidence == 0.85

    def test_confidence_default(self) -> None:
        """Given confidence 미지정 When Evidence 생성 Then 기본 0.0"""
        prov = Provenance(
            channel="test",
            source_id="0",
            url="https://test.com",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        ev = Evidence(
            field="dong", value="101동", pillar=Pillar.LEDGER, provenance=prov
        )
        assert ev.confidence == 0.0

    def test_confidence_below_zero_raises(self) -> None:
        """Given confidence < 0 When Evidence 생성 Then ValueError"""
        prov = Provenance(
            channel="test",
            source_id="0",
            url="https://test.com",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        with pytest.raises(ValueError, match="confidence"):
            Evidence(
                field="ho",
                value="101",
                pillar=Pillar.UNIT_RESOLUTION,
                provenance=prov,
                confidence=-0.1,
            )

    def test_confidence_above_one_raises(self) -> None:
        """Given confidence > 1 When Evidence 생성 Then ValueError"""
        prov = Provenance(
            channel="test",
            source_id="0",
            url="https://test.com",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        with pytest.raises(ValueError, match="confidence"):
            Evidence(
                field="ho",
                value="101",
                pillar=Pillar.UNIT_RESOLUTION,
                provenance=prov,
                confidence=1.5,
            )

    def test_confidence_edge_case(self) -> None:
        """Given confidence=0.0 또는 1.0 When Evidence 생성 Then 정상"""
        prov = Provenance(
            channel="test",
            source_id="0",
            url="https://test.com",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        ev_low = Evidence(
            field="ho",
            value="101",
            pillar=Pillar.UNIT_RESOLUTION,
            provenance=prov,
            confidence=0.0,
        )
        ev_high = Evidence(
            field="ho",
            value="101",
            pillar=Pillar.UNIT_RESOLUTION,
            provenance=prov,
            confidence=1.0,
        )
        assert ev_low.confidence == 0.0
        assert ev_high.confidence == 1.0


class TestListing:
    """Listing 생성."""

    def test_create_with_all_fields(self) -> None:
        """Given 모든 필드 When Listing 생성 Then 정상 생성"""
        from datetime import datetime, timezone

        prov = Provenance(
            channel="naver",
            source_id="article123",
            url="https://naver.com/article123",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        listing = Listing(
            complex_id="C1001",
            dong="101",
            floor_info="23",
            floor_kind=FloorKind.EXACT,
            area2=84.5,
            direction="S",
            trade_type=TradeType.JEONSE,
            price_manwon=45000,
            ho_hint="102호",
            provenance=prov,
        )
        assert listing.complex_id == "C1001"
        assert listing.dong == "101"
        assert listing.floor_info == "23"
        assert listing.floor_kind == FloorKind.EXACT
        assert listing.area2 == 84.5
        assert listing.direction == "S"
        assert listing.trade_type == TradeType.JEONSE
        assert listing.price_manwon == 45000
        assert listing.ho_hint == "102호"
        assert listing.provenance is prov

    def test_create_with_minimal_fields(self) -> None:
        """Given 최소 필드 When Listing 생성 Then 정상 생성 (ho_hint=None 기본)"""
        listing = Listing(
            complex_id="C1002",
            dong="102",
            floor_info="저/5",
            floor_kind=FloorKind.LOW,
            area2=59.0,
            direction="E",
            trade_type=TradeType.WOLSE,
            price_manwon=5000,
        )
        assert listing.complex_id == "C1002"
        assert listing.ho_hint is None
        assert listing.provenance is None


class TestHoConclusion:
    """HoConclusion 생성 및 is_estimate 기본값."""

    def test_is_estimate_default_true(self) -> None:
        """Given is_estimate 미지정 When HoConclusion 생성 Then 기본 True"""
        hc = HoConclusion(
            complex_id="C1001",
            dong="101",
        )
        assert hc.is_estimate is True

    def test_is_estimate_explicit_false(self) -> None:
        """Given is_estimate=False When HoConclusion 생성 Then False 유지"""
        hc = HoConclusion(
            complex_id="C1001",
            dong="101",
            is_estimate=False,
        )
        assert hc.is_estimate is False

    def test_default_fields(self) -> None:
        """Given 최소 필드 When HoConclusion 생성 Then 기본값 확인"""
        hc = HoConclusion(complex_id="C1001", dong="101")
        assert hc.complex_id == "C1001"
        assert hc.dong == "101"
        assert hc.candidate_hos == []
        assert hc.ho_final is None
        assert hc.grade == "none"
        assert hc.evidence == []
        assert hc.method_log == []

    def test_with_candidates_and_evidence(self) -> None:
        """Given 후보 호와 증거 When HoConclusion 생성 Then 모두 저장"""
        prov = Provenance(
            channel="test",
            source_id="0",
            url="https://test.com",
            captured_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        )
        ev = Evidence(
            field="ho",
            value="101",
            pillar=Pillar.UNIT_RESOLUTION,
            provenance=prov,
            confidence=0.9,
        )
        hc = HoConclusion(
            complex_id="C1001",
            dong="101",
            candidate_hos=[{"ho": "101", "probability": 0.85}, {"ho": "102", "probability": 0.15}],
            ho_final="101",
            grade="확정",
            is_estimate=False,
            evidence=[ev],
            method_log=["unit_resolution → 101호"],
        )
        assert len(hc.candidate_hos) == 2
        assert hc.candidate_hos[0]["ho"] == "101"
        assert hc.candidate_hos[0]["probability"] == 0.85
        assert hc.ho_final == "101"
        assert hc.grade == "확정"
        assert len(hc.evidence) == 1
        assert hc.evidence[0] is ev
        assert hc.method_log == ["unit_resolution → 101호"]


class TestEnums:
    """Enum 기본값 확인."""

    def test_pillar_values(self) -> None:
        assert Pillar.UNIT_RESOLUTION.value == "unit_resolution"
        assert Pillar.HO_COMPLETION.value == "ho_completion"
        assert Pillar.CLOSURE_LABEL.value == "closure_label"
        assert Pillar.LEDGER.value == "ledger"

    def test_floor_kind_values(self) -> None:
        assert FloorKind.EXACT.value == "exact"
        assert FloorKind.LOW.value == "low"
        assert FloorKind.MID.value == "mid"
        assert FloorKind.HIGH.value == "high"

    def test_trade_type_values(self) -> None:
        assert TradeType.SALE.value == "sale"
        assert TradeType.JEONSE.value == "jeonse"
        assert TradeType.WOLSE.value == "wolse"


class TestNormalizeDirection:
    """normalize_direction 함수."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("남향", "S"),
            ("북향", "N"),
            ("동향", "E"),
            ("서향", "W"),
            ("남동향", "SE"),
            ("남서향", "SW"),
            ("북동향", "NE"),
            ("북서향", "NW"),
        ],
    )
    def test_valid_directions(self, raw: str, expected: str) -> None:
        """Given 유효한 한글 방향 When normalize_direction Then 영문 코드 반환"""
        assert normalize_direction(raw) == expected

    def test_invalid_direction_raises(self) -> None:
        """Given 알 수 없는 방향 When normalize_direction Then ValueError"""
        with pytest.raises(ValueError, match="알 수 없는 방향"):
            normalize_direction("북남향")


class TestParseFloor:
    """parse_floor 함수."""

    @pytest.mark.parametrize(
        ("raw", "expected_kind", "expected_num"),
        [
            ("23", FloorKind.EXACT, 23),
            ("1", FloorKind.EXACT, 1),
            ("저/23", FloorKind.LOW, 23),
            ("저/5", FloorKind.LOW, 5),
            ("고/15", FloorKind.HIGH, 15),
            ("고/33", FloorKind.HIGH, 33),
            ("중", FloorKind.MID, None),
        ],
    )
    def test_valid_floors(
        self, raw: str, expected_kind: FloorKind, expected_num: int | None
    ) -> None:
        """Given 유효한 층 문자열 When parse_floor Then (Kind, 층번호) 반환"""
        kind, num = parse_floor(raw)
        assert kind == expected_kind
        assert num == expected_num
