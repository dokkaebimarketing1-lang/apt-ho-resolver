"""Tracker + HoState 단위 테스트.

테스트 전략:
- HoState: frozen dataclass, 상태 검증, 유효 상태만 허용
- Tracker: 기록·조회·diff·공실 추론·미끼 탐지·유령 필터
- 데이터 삭제 로직 없음 확인 (delete/remove 메서드 없음)
- 모든 상태 5종 영구 저장 확인
- 공실 = 음의 증거 (매칭 시 후보 제외)
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.tracker import (
    BAIT_HIGH_DAYS,
    BAIT_LOW_DAYS,
    BAIT_MID_DAYS,
    HoState,
    Tracker,
    VALID_STATUSES,
)


# ============================================================
# Test: HoState dataclass
# ============================================================


class TestHoState:
    """HoState frozen dataclass 기본 동작."""

    def test_is_frozen_dataclass(self) -> None:
        """Given HoState class Then frozen dataclass."""
        import dataclasses
        assert dataclasses.is_dataclass(HoState)
        assert dataclasses.fields(HoState)

    def test_create_ho_state(self) -> None:
        """Given 모든 필드 When 생성 Then 속성 제공."""
        now = datetime(2026, 6, 29, 12, 0, 0)
        state = HoState(
            complex_id="C1",
            canonical_ho_id="1503",
            status="occupied",
            observed_at=now,
            source="inspection",
            metadata={"floor": 15, "area": 84.12},
        )
        assert state.complex_id == "C1"
        assert state.canonical_ho_id == "1503"
        assert state.status == "occupied"
        assert state.observed_at == now
        assert state.source == "inspection"
        assert state.metadata == {"floor": 15, "area": 84.12}

    def test_frozen_cannot_modify(self) -> None:
        """Given HoState When 속성 설정 Then FrozenInstanceError."""
        state = HoState(
            complex_id="C1",
            canonical_ho_id="1503",
            status="vacant",
            observed_at=datetime.now(),
            source="test",
        )
        with pytest.raises(AttributeError):
            state.status = "occupied"  # type: ignore[misc]

    def test_invalid_status_raises(self) -> None:
        """Given 알 수 없는 상태 When HoState 생성 Then ValueError."""
        with pytest.raises(ValueError, match="알 수 없는 상태"):
            HoState(
                complex_id="C1",
                canonical_ho_id="1503",
                status="unknown_status",
                observed_at=datetime.now(),
                source="test",
            )

    def test_all_valid_statuses(self) -> None:
        """Given 5개 유효 상태 When 각각 생성 Then 정상."""
        now = datetime.now()
        for status in sorted(VALID_STATUSES):
            state = HoState(
                complex_id="C1",
                canonical_ho_id="1503",
                status=status,
                observed_at=now,
                source="test",
            )
            assert state.status == status

    def test_metadata_default_empty(self) -> None:
        """Given metadata 미제공 When 생성 Then 빈 dict."""
        state = HoState(
            complex_id="C1",
            canonical_ho_id="1503",
            status="sold",
            observed_at=datetime.now(),
            source="test",
        )
        assert state.metadata == {}

    def test_5_statuses_mapped(self) -> None:
        """Given 5상태 When 확인 Then occupied/vacant/for_sale/for_rent/sold."""
        expected = frozenset({"occupied", "vacant", "for_sale", "for_rent", "sold"})
        assert VALID_STATUSES == expected


# ============================================================
# Test: Tracker — record_observation
# ============================================================


class TestRecordObservation:
    """record_observation — 상태 기록."""

    def test_record_returns_ho_state(self) -> None:
        """Given Tracker When record_observation Then HoState 반환."""
        tracker = Tracker()
        state = tracker.record_observation(
            complex_id="C1",
            canonical_ho_id="1503",
            status="occupied",
            source="inspection",
        )
        assert isinstance(state, HoState)
        assert state.complex_id == "C1"
        assert state.canonical_ho_id == "1503"
        assert state.status == "occupied"
        assert state.source == "inspection"

    def test_record_stores_state(self) -> None:
        """Given 기록 후 When get_state_history Then 저장된 상태 확인."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "occupied", "inspection")
        history = tracker.get_state_history("C1", "1503")
        assert len(history) == 1
        assert history[0].status == "occupied"

    def test_record_multiple_observations(self) -> None:
        """Given 여러 관측 When 기록 Then 모두 저장."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "occupied", "src_a")
        tracker.record_observation("C1", "1503", "for_sale", "src_b")
        tracker.record_observation("C1", "1503", "sold", "src_c")
        history = tracker.get_state_history("C1", "1503")
        assert len(history) == 3

    def test_record_with_metadata(self) -> None:
        """Given metadata When 기록 Then metadata 보존."""
        tracker = Tracker()
        meta = {"price_manwon": 100000, "agent": "zigbang"}
        state = tracker.record_observation(
            "C1", "1503", "for_sale", "zigbang", metadata=meta,
        )
        assert state.metadata == meta

    def test_record_without_metadata(self) -> None:
        """Given metadata=None When 기록 Then 빈 dict."""
        tracker = Tracker()
        state = tracker.record_observation("C1", "1503", "vacant", "inspection")
        assert state.metadata == {}

    def test_invalid_status_raises(self) -> None:
        """Given 유효하지 않은 상태 When 기록 Then ValueError."""
        tracker = Tracker()
        with pytest.raises(ValueError):
            tracker.record_observation("C1", "1503", "not_a_status", "test")


# ============================================================
# Test: Tracker — get_current_state
# ============================================================


class TestGetCurrentState:
    """get_current_state — 최신 상태 조회."""

    def test_current_state_after_single(self) -> None:
        """Given 1회 기록 When get_current_state Then 최신 상태 반환."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "occupied", "src_a")
        current = tracker.get_current_state("C1", "1503")
        assert current is not None
        assert current.status == "occupied"

    def test_current_returns_latest(self) -> None:
        """Given 여러 관측 When get_current_state Then 최신 상태 반환."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "occupied", "src_a")
        tracker.record_observation("C1", "1503", "for_sale", "src_b")
        current = tracker.get_current_state("C1", "1503")
        assert current is not None
        assert current.status == "for_sale"

    def test_current_none_for_no_history(self) -> None:
        """Given 기록 없음 When get_current_state Then None."""
        tracker = Tracker()
        assert tracker.get_current_state("C1", "9999") is None

    def test_current_isolated_per_ho(self) -> None:
        """Given 여러 호 When get_current_state Then 각각 독립."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "sold", "src_a")
        tracker.record_observation("C1", "1504", "for_sale", "src_b")
        assert tracker.get_current_state("C1", "1503") is not None
        assert tracker.get_current_state("C1", "1504") is not None
        assert tracker.get_current_state("C1", "9999") is None


# ============================================================
# Test: Tracker — get_state_history
# ============================================================


class TestGetStateHistory:
    """get_state_history — 전체 이력 조회."""

    def test_empty_history(self) -> None:
        """Given 기록 없음 When get_state_history Then 빈 리스트."""
        tracker = Tracker()
        assert tracker.get_state_history("C1", "9999") == []

    def test_history_returns_all(self) -> None:
        """Given 3회 기록 When get_state_history Then 3개 반환."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "occupied", "src_a")
        tracker.record_observation("C1", "1503", "for_sale", "src_b")
        tracker.record_observation("C1", "1503", "sold", "src_c")
        history = tracker.get_state_history("C1", "1503")
        assert len(history) == 3

    def test_history_sorted_by_observed_at(self) -> None:
        """Given 기록 When get_state_history Then 시간순 정렬."""
        tracker = Tracker()
        # 기록 순서와 무관하게 observed_at 기준 정렬
        # observed_at은 record_observation에서 자동으로 now() 사용
        # 여러 번 호출하므로 시간순 정렬 보장됨
        s1 = tracker.record_observation("C1", "1503", "occupied", "src_a")
        s2 = tracker.record_observation("C1", "1503", "for_sale", "src_b")
        s3 = tracker.record_observation("C1", "1503", "sold", "src_c")
        history = tracker.get_state_history("C1", "1503")
        assert history[0] is s1
        assert history[1] is s2
        assert history[2] is s3

    def test_history_preserves_all_data(self) -> None:
        """Given 기록 When history Then 모든 필드 보존."""
        tracker = Tracker()
        meta = {"price": 100000}
        tracker.record_observation("C1", "1503", "for_sale", "zigbang", metadata=meta)
        history = tracker.get_state_history("C1", "1503")
        assert len(history) == 1
        s = history[0]
        assert s.complex_id == "C1"
        assert s.canonical_ho_id == "1503"
        assert s.status == "for_sale"
        assert s.source == "zigbang"
        assert s.metadata == meta


# ============================================================
# Test: Tracker — detect_disappeared
# ============================================================


class TestDetectDisappeared:
    """detect_disappeared — 스냅샷 diff."""

    def test_no_disappeared(self) -> None:
        """Given 현재=이전 When detect_disappeared Then 빈 리스트."""
        tracker = Tracker()
        current = [
            {"complex_id": "C1", "ho_id": "1503"},
            {"complex_id": "C1", "ho_id": "1504"},
        ]
        previous = [
            {"complex_id": "C1", "ho_id": "1503"},
            {"complex_id": "C1", "ho_id": "1504"},
        ]
        result = tracker.detect_disappeared(current, previous)
        assert result == []

    def test_one_disappeared(self) -> None:
        """Given 이전에만 있는 매물 When detect_disappeared Then 탐지."""
        tracker = Tracker()
        current = [
            {"complex_id": "C1", "ho_id": "1503"},
        ]
        previous = [
            {"complex_id": "C1", "ho_id": "1503"},
            {"complex_id": "C1", "ho_id": "1504"},
        ]
        result = tracker.detect_disappeared(current, previous)
        assert len(result) == 1
        assert result[0]["ho_id"] == "1504"

    def test_multiple_disappeared(self) -> None:
        """Given 2개 사라짐 When detect_disappeared Then 2개 탐지."""
        tracker = Tracker()
        current: list[dict] = [
            {"complex_id": "C1", "ho_id": "1501"},
        ]
        previous = [
            {"complex_id": "C1", "ho_id": "1501"},
            {"complex_id": "C1", "ho_id": "1502"},
            {"complex_id": "C1", "ho_id": "1503"},
        ]
        result = tracker.detect_disappeared(current, previous)
        assert len(result) == 2
        ids = {r["ho_id"] for r in result}
        assert ids == {"1502", "1503"}

    def test_empty_current(self) -> None:
        """Given 현재=빈 리스트 When detect_disappeared Then 이전 모두 반환."""
        tracker = Tracker()
        previous = [
            {"complex_id": "C1", "ho_id": "1503"},
            {"complex_id": "C1", "ho_id": "1504"},
        ]
        result = tracker.detect_disappeared([], previous)
        assert len(result) == 2

    def test_empty_previous(self) -> None:
        """Given 이전=빈 리스트 When detect_disappeared Then 빈 리스트."""
        tracker = Tracker()
        current = [{"complex_id": "C1", "ho_id": "1503"}]
        result = tracker.detect_disappeared(current, [])
        assert result == []

    def test_missing_keys_handled(self) -> None:
        """Given dict에 키 누락 When detect_disappeared Then 기본값 처리."""
        tracker = Tracker()
        current: list[dict] = []
        previous = [
            {"complex_id": "C1"},  # ho_id 없음
            {"ho_id": "1503"},     # complex_id 없음
        ]
        result = tracker.detect_disappeared(current, previous)
        assert len(result) == 2


# ============================================================
# Test: Tracker — classify_vacancy
# ============================================================


class TestClassifyVacancy:
    """classify_vacancy — 공실 추론."""

    def test_transacted_when_sold(self) -> None:
        """Given 거래성사 기록 When classify_vacancy Then transacted."""
        tracker = Tracker()
        now = datetime.now()
        states = [
            HoState("C1", "1503", "sold", now, "src_a"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "transacted"

    def test_active_when_for_sale(self) -> None:
        """Given 매도 기록 When classify_vacancy Then active."""
        tracker = Tracker()
        now = datetime.now()
        states = [
            HoState("C1", "1503", "for_sale", now, "src_a"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "active"

    def test_active_when_for_rent(self) -> None:
        """Given 임대 기록 When classify_vacancy Then active."""
        tracker = Tracker()
        now = datetime.now()
        states = [
            HoState("C1", "1503", "for_rent", now, "src_a"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "active"

    def test_active_when_occupied(self) -> None:
        """Given 거주 기록 When classify_vacancy Then active."""
        tracker = Tracker()
        now = datetime.now()
        states = [
            HoState("C1", "1503", "occupied", now, "src_a"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "active"

    def test_vacancy_candidate(self) -> None:
        """Given 공실 기록만 When classify_vacancy Then vacancy_candidate."""
        tracker = Tracker()
        now = datetime.now()
        states = [
            HoState("C1", "1503", "vacant", now, "src_a"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "vacancy_candidate"

    def test_unknown_for_empty(self) -> None:
        """Given 빈 리스트 When classify_vacancy Then unknown."""
        tracker = Tracker()
        result = tracker.classify_vacancy([])
        assert result["vacancy_status"] == "unknown"

    def test_sold_overrides_vacancy(self) -> None:
        """Given sold + vacant When classify_vacancy Then transacted 우선."""
        tracker = Tracker()
        states = [
            HoState("C1", "1503", "vacant", datetime.now(), "src_a"),
            HoState("C1", "1503", "sold", datetime.now(), "src_b"),
        ]
        result = tracker.classify_vacancy(states)
        # sold 우선
        assert result["vacancy_status"] == "transacted"

    def test_vacancy_candidate_is_negative_evidence(self) -> None:
        """Given vacancy_candidate When 매칭 Then 음의 증거로 취급.

        공실 후보는 매칭 시 후보에서 제외되어야 함.
        classify_vacancy가 "vacancy_candidate" 반환 = 음의 증거.
        """
        tracker = Tracker()
        now = datetime.now()
        states = [
            HoState("C1", "1503", "vacant", now, "lh_vacancy"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "vacancy_candidate"
        # vacancy_candidate = 공실 후보 = 매칭 제외 대상
        result_str = result["vacancy_status"]
        assert result_str == "vacancy_candidate"
        reason = result.get("reason", "")
        assert "음의 증거" in reason


# ============================================================
# Test: Tracker — compute_bait_score
# ============================================================


class TestComputeBaitScore:
    """compute_bait_score — 미끼 매물 의심도."""

    def test_low_no_first_seen(self) -> None:
        """Given first_seen_at 없음 When compute_bait_score Then LOW."""
        tracker = Tracker()
        listing: dict = {"complex_id": "C1", "ho_id": "1503"}
        assert tracker.compute_bait_score(listing) == "LOW"

    def test_low_recent(self) -> None:
        """Given 30일 미만 When compute_bait_score Then LOW."""
        tracker = Tracker()
        recent = (datetime.now() - timedelta(days=30)).isoformat()
        listing = {"complex_id": "C1", "ho_id": "1503", "first_seen_at": recent}
        assert tracker.compute_bait_score(listing) == "LOW"

    def test_low_null_first_seen(self) -> None:
        """Given first_seen_at=None When compute_bait_score Then LOW."""
        tracker = Tracker()
        listing = {"complex_id": "C1", "ho_id": "1503", "first_seen_at": None}
        assert tracker.compute_bait_score(listing) == "LOW"

    def test_mid_90_days(self) -> None:
        """Given 90일 경과 When compute_bait_score Then MID."""
        tracker = Tracker()
        past = (datetime.now() - timedelta(days=BAIT_LOW_DAYS)).isoformat()
        listing = {"complex_id": "C1", "ho_id": "1503", "first_seen_at": past}
        assert tracker.compute_bait_score(listing) == "MID"

    def test_mid_180_days(self) -> None:
        """Given 180일 경과 When compute_bait_score Then MID."""
        tracker = Tracker()
        past = (datetime.now() - timedelta(days=BAIT_MID_DAYS)).isoformat()
        listing = {"complex_id": "C1", "ho_id": "1503", "first_seen_at": past}
        assert tracker.compute_bait_score(listing) == "MID"

    def test_high_365_days(self) -> None:
        """Given 365일 경과 When compute_bait_score Then HIGH."""
        tracker = Tracker()
        past = (datetime.now() - timedelta(days=BAIT_HIGH_DAYS)).isoformat()
        listing = {"complex_id": "C1", "ho_id": "1503", "first_seen_at": past}
        assert tracker.compute_bait_score(listing) == "HIGH"

    def test_high_over_one_year(self) -> None:
        """Given 400일 경과 When compute_bait_score Then HIGH."""
        tracker = Tracker()
        past = (datetime.now() - timedelta(days=400)).isoformat()
        listing = {"complex_id": "C1", "ho_id": "1503", "first_seen_at": past}
        assert tracker.compute_bait_score(listing) == "HIGH"

    def test_datetime_first_seen(self) -> None:
        """Given first_seen_at=datetime When compute_bait_score Then 정상."""
        tracker = Tracker()
        past = datetime.now() - timedelta(days=30)
        listing = {"complex_id": "C1", "ho_id": "1503", "first_seen_at": past}
        assert tracker.compute_bait_score(listing) == "LOW"

    def test_invalid_date_string(self) -> None:
        """Given 잘못된 날짜 문자열 When compute_bait_score Then LOW."""
        tracker = Tracker()
        listing = {
            "complex_id": "C1",
            "ho_id": "1503",
            "first_seen_at": "not-a-date",
        }
        assert tracker.compute_bait_score(listing) == "LOW"


# ============================================================
# Test: Tracker — filter_ghost_listings
# ============================================================


class TestFilterGhostListings:
    """filter_ghost_listings — 유령 매물 필터."""

    def test_all_valid_with_2_observations(self) -> None:
        """Given 2회 관측된 매물 When filter_ghost_listings Then 유지."""
        tracker = Tracker()
        listings = [
            {"complex_id": "C1", "ho_id": "1503"},
            {"complex_id": "C1", "ho_id": "1503"},
        ]
        result = tracker.filter_ghost_listings(listings, min_observations=2)
        assert len(result) == 2  # 두 건 모두 유지

    def test_single_observation_filtered(self) -> None:
        """Given 1회 관측 When filter_ghost_listings(min=2) Then 제거."""
        tracker = Tracker()
        listings = [
            {"complex_id": "C1", "ho_id": "1503"},
        ]
        result = tracker.filter_ghost_listings(listings, min_observations=2)
        assert result == []

    def test_mixed_observations(self) -> None:
        """Given 혼합 When filter_ghost_listings Then 적절히 필터."""
        tracker = Tracker()
        listings = [
            {"complex_id": "C1", "ho_id": "1503"},  # 2회 → 유지
            {"complex_id": "C1", "ho_id": "1503"},  # 2회
            {"complex_id": "C1", "ho_id": "1504"},  # 1회 → 제거
            {"complex_id": "C2", "ho_id": "1001"},  # 2회 → 유지
            {"complex_id": "C2", "ho_id": "1001"},  # 2회
        ]
        result = tracker.filter_ghost_listings(listings, min_observations=2)
        assert len(result) == 4
        assert all(l["ho_id"] in ("1503", "1001") for l in result)

    def test_custom_min_observations(self) -> None:
        """Given min_observations=3 When filter_ghost_listings Then 3회 이상만."""
        tracker = Tracker()
        listings = [
            {"complex_id": "C1", "ho_id": "1503"},  # 3회 → 유지
            {"complex_id": "C1", "ho_id": "1503"},
            {"complex_id": "C1", "ho_id": "1503"},
            {"complex_id": "C1", "ho_id": "1504"},  # 2회 → 제거
            {"complex_id": "C1", "ho_id": "1504"},
        ]
        result = tracker.filter_ghost_listings(listings, min_observations=3)
        assert len(result) == 3
        assert all(l["ho_id"] == "1503" for l in result)

    def test_empty_list(self) -> None:
        """Given 빈 리스트 When filter_ghost_listings Then 빈 리스트."""
        tracker = Tracker()
        assert tracker.filter_ghost_listings([]) == []

    def test_missing_keys(self) -> None:
        """Given 키 누락 When filter_ghost_listings Then 기본값 처리."""
        tracker = Tracker()
        listings: list[dict] = [
            {},           # 키 없음
            {},           # 키 없음 (2회 → 유지)
            {"ho_id": "x"},  # complex_id 없음 (1회 → 제거)
        ]
        result = tracker.filter_ghost_listings(listings, min_observations=2)
        assert len(result) == 2


# ============================================================
# Test: 데이터 삭제 로직 없음 확인
# ============================================================


class TestNoDeleteLogic:
    """Tracker에 delete/remove/clear 메서드 없음 확인."""

    def test_no_delete_method(self) -> None:
        """Given Tracker Then delete 메서드 없음."""
        forbidden = {"delete", "remove", "clear", "purge", "expire", "truncate"}
        tracker_attrs = {name for name in dir(Tracker) if not name.startswith("_")}
        found = forbidden & tracker_attrs
        assert not found, f"삭제 메서드 발견: {found}"

    def test_no_del_method(self) -> None:
        """Given Tracker Then __del__ 메서드 없음."""
        assert not hasattr(Tracker, "__del__")

    def test_ho_state_no_delete(self) -> None:
        """Given HoState Then __del__ 메서드 없음."""
        assert not hasattr(HoState, "__del__")


# ============================================================
# Test: 모든 상태(5종) 영구 저장 확인
# ============================================================


class TestAllStatusesPersisted:
    """5개 상태 모두 영구 저장 확인."""

    def test_all_5_statuses_can_be_recorded(self) -> None:
        """Given 5개 상태 When record_observation Then 모두 저장."""
        tracker = Tracker()
        statuses = ["occupied", "vacant", "for_sale", "for_rent", "sold"]
        for i, status in enumerate(statuses):
            tracker.record_observation(f"C1", f"150{i+1}", status, "test")
        for i, status in enumerate(statuses):
            current = tracker.get_current_state(f"C1", f"150{i+1}")
            assert current is not None
            assert current.status == status

    def test_all_statuses_in_history(self) -> None:
        """Given 5개 상태 1개 호 When get_state_history Then 모두 보존."""
        tracker = Tracker()
        statuses = ["occupied", "vacant", "for_sale", "for_rent", "sold"]
        for status in statuses:
            tracker.record_observation("C1", "1503", status, "test")
        history = tracker.get_state_history("C1", "1503")
        assert len(history) == 5
        recorded = [s.status for s in history]
        assert recorded == statuses


# ============================================================
# Test: 거래성사 → CLOSURE_LABEL 정답 라벨 (interface 설계)
# ============================================================


class TestTransactionClosedLabel:
    """sold(거래성사) → 정답 라벨 생성 인터페이스."""

    def test_sold_state_creates_closure_label(self) -> None:
        """Given 거래성사 기록 When 상태 생성 Then line_fact 적립 가능."""
        tracker = Tracker()
        state = tracker.record_observation("C1", "1503", "sold", "rtms_registry")
        assert state.status == "sold"
        assert state.source == "rtms_registry"
        # sold 상태는 CLOSURE_LABEL 생성 조건:
        # 추후 matcher가 sold 상태 발견 시 line_fact에 정답 라벨 적립
        # (실제 적립은 matcher 책임 — Tracker는 상태만 저장)
        assert hasattr(state, "status")
        assert state.status == "sold"

    def test_current_state_after_sold(self) -> None:
        """Given 거래성사 후 When get_current_state Then sold."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "occupied", "src_a")
        tracker.record_observation("C1", "1503", "for_sale", "src_b")
        tracker.record_observation("C1", "1503", "sold", "rtms")
        current = tracker.get_current_state("C1", "1503")
        assert current is not None
        assert current.status == "sold"
        assert current.source == "rtms"


# ============================================================
# Test: 공실 호 → 매칭 후보 제외 (interface 설계)
# ============================================================


class TestVacancyExcludedFromMatching:
    """vacancy_candidate → 매칭 시 후보 제외 로직."""

    def test_vacancy_candidate_result(self) -> None:
        """Given 공실 기록 When classify_vacancy Then vacancy_candidate."""
        tracker = Tracker()
        states = [
            HoState("C1", "1503", "vacant", datetime.now(), "lh"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "vacancy_candidate"

    def test_vacant_different_from_active(self) -> None:
        """Given 공실 When classify_vacancy Then active와 구분."""
        tracker = Tracker()
        vacant_states = [
            HoState("C1", "1503", "vacant", datetime.now(), "lh"),
        ]
        active_states = [
            HoState("C1", "1504", "for_sale", datetime.now(), "zigbang"),
        ]
        vacant_result = tracker.classify_vacancy(vacant_states)
        active_result = tracker.classify_vacancy(active_states)
        assert vacant_result["vacancy_status"] == "vacancy_candidate"
        assert active_result["vacancy_status"] == "active"

    def test_vacancy_negative_evidence_label(self) -> None:
        """Given vacancy_candidate Then 음의 증거 레이블 확인."""
        tracker = Tracker()
        states = [
            HoState("C1", "1503", "vacant", datetime.now(), "lh"),
        ]
        result = tracker.classify_vacancy(states)
        assert result["vacancy_status"] == "vacancy_candidate"
        # 음의 증거 = 매칭 시 해당 호를 후보에서 제외
        # (실제 제외는 matcher가 수행 — Tracker는 추론 결과만 제공)


# ============================================================
# Test: Tracker 기본 속성
# ============================================================


class TestTrackerBasics:
    """Tracker 기본 동작."""

    def test_tracker_initial_state_empty(self) -> None:
        """Given Tracker 생성 When 확인 Then 빈 상태."""
        tracker = Tracker()
        assert hasattr(tracker, "_states")
        assert isinstance(tracker._states, dict)
        assert len(tracker._states) == 0

    def test_get_current_none_for_unknown(self) -> None:
        """Given 알 수 없는 호 When get_current_state Then None."""
        tracker = Tracker()
        assert tracker.get_current_state("NONEXIST", "9999") is None

    def test_different_complex_same_ho_independent(self) -> None:
        """Given 다른 단지 같은 호 When 기록 Then 독립."""
        tracker = Tracker()
        tracker.record_observation("C1", "1503", "occupied", "src_a")
        tracker.record_observation("C2", "1503", "vacant", "src_b")
        assert tracker.get_current_state("C1", "1503").status == "occupied"  # type: ignore[union-attr]
        assert tracker.get_current_state("C2", "1503").status == "vacant"  # type: ignore[union-attr]


# ============================================================
# Test: tracker 모듈 상수
# ============================================================


class TestConstants:
    """tracker.py 모듈 상수 검증."""

    def test_bait_day_constants(self) -> None:
        """Given 미끼 임계 상수 Then 올바른 값."""
        assert BAIT_LOW_DAYS == 90
        assert BAIT_MID_DAYS == 180
        assert BAIT_HIGH_DAYS == 365

    def test_bait_ordering(self) -> None:
        """Given 미끼 임계 When 비교 Then LOW < MID < HIGH."""
        assert BAIT_LOW_DAYS < BAIT_MID_DAYS < BAIT_HIGH_DAYS
