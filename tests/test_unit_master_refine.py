"""unit_master 정제 모듈 테스트 (Todo 34).

테스트 범위:
- deduplicate: canonical_ho_id 기준 그룹화
- _resolve_field: 우선순위 기반 충돌 해결
- resolve_conflicts: 전체 행 충돌 해결
- refine_unit_master: 전체 파이프라인
"""

from __future__ import annotations

import pytest

from src.ingest.unit_master_refine import (
    SOURCE_PRIORITY,
    _resolve_field,
    deduplicate,
    refine_unit_master,
    resolve_conflicts,
)


class TestSourcePriority:
    def test_registry_highest(self):
        """등기부가 최우선 우선순위."""
        assert SOURCE_PRIORITY["registry"] > SOURCE_PRIORITY["public_price"]
        assert SOURCE_PRIORITY["registry"] > SOURCE_PRIORITY["building_registry"]
        assert SOURCE_PRIORITY["registry"] > SOURCE_PRIORITY["housing_permit"]

    def test_priority_order(self):
        """우선순위: registry > public_price > building_registry > housing_permit."""
        p = SOURCE_PRIORITY
        assert p["registry"] > p["public_price"] > p["building_registry"] > p["housing_permit"]


class TestDeduplicate:
    def test_single_group(self):
        """한 그룹에 3개 행 — 모두 같은 canonical_ho_id."""
        rows = [
            {"canonical_ho_id": "1503", "source": "public_price"},
            {"canonical_ho_id": "1503", "source": "building_registry"},
            {"canonical_ho_id": "1503", "source": "housing_permit"},
        ]
        groups = deduplicate(rows)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_multiple_groups(self):
        """3개 그룹 — 각각 다른 canonical_ho_id."""
        rows = [
            {"canonical_ho_id": "1503", "source": "public_price"},
            {"canonical_ho_id": "1504", "source": "public_price"},
            {"canonical_ho_id": "1505", "source": "building_registry"},
        ]
        groups = deduplicate(rows)
        assert len(groups) == 3
        assert all(len(g) == 1 for g in groups)

    def test_missing_key(self):
        """canonical_ho_id 없는 행은 그룹화 제외."""
        rows = [
            {"canonical_ho_id": "1503"},
            {"other_field": "value"},
            {"canonical_ho_id": ""},
        ]
        groups = deduplicate(rows)
        assert len(groups) == 1  # 하나만 유효

    def test_empty_rows(self):
        assert deduplicate([]) == []


class TestResolveField:
    def test_same_value_no_conflict(self):
        """모든 소스 동일한 값 → 충돌 없음."""
        rows = [
            {"dong": "101", "source": "public_price"},
            {"dong": "101", "source": "building_registry"},
            {"dong": "101", "source": "housing_permit"},
        ]
        assert _resolve_field("dong", rows) == "101"

    def test_registry_wins(self):
        """등기부 "102" vs 공시 "101" → 등기부 우선."""
        rows = [
            {"dong": "101", "source": "public_price"},
            {"dong": "102", "source": "registry"},
        ]
        assert _resolve_field("dong", rows) == "102"

    def test_public_price_over_building_registry(self):
        """공시가격 vs 대장 → 공시가격 우선."""
        rows = [
            {"floor": 15, "source": "building_registry"},
            {"floor": 14, "source": "public_price"},
        ]
        assert _resolve_field("floor", rows) == 14

    def test_missing_field(self):
        """한 소스에 필드 없음 → 있는 소스 값 사용."""
        rows = [
            {"dong": "101", "source": "public_price"},
            {"source": "building_registry"},  # dong 없음
        ]
        assert _resolve_field("dong", rows) == "101"

    def test_all_none(self):
        """모든 값 None → None 반환."""
        rows = [
            {"area_type": None, "source": "public_price"},
            {"area_type": None, "source": "building_registry"},
        ]
        assert _resolve_field("area_type", rows) is None


class TestResolveConflicts:
    def test_no_conflict(self):
        """모든 필드 동일 → 충돌 0."""
        rows = [
            {
                "canonical_ho_id": "1503",
                "complex_id": "C1",
                "ho": "1503",
                "dong": "101",
                "floor": 15,
                "area_exclusive": 8400,
                "area_type": "84A",
                "direction": "S",
                "source": "public_price",
            },
            {
                "canonical_ho_id": "1503",
                "complex_id": "C1",
                "ho": "1503",
                "dong": "101",
                "floor": 15,
                "area_exclusive": 8400,
                "area_type": "84A",
                "direction": "S",
                "source": "building_registry",
            },
        ]
        resolved = resolve_conflicts(rows)
        assert resolved["_conflict_count"] == 0
        assert resolved["dong"] == "101"
        assert resolved["floor"] == 15
        assert resolved["source"] == ["building_registry", "public_price"]

    def test_dong_conflict(self):
        """동 충돌 → 등기부 우선."""
        rows = [
            {"canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
             "dong": "101", "source": "public_price"},
            {"canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
             "dong": "102", "source": "registry"},
        ]
        resolved = resolve_conflicts(rows)
        assert resolved["dong"] == "102"  # registry wins
        assert resolved["_conflict_count"] > 0

    def test_area_conflict(self):
        """면적 충돌 → 공시가격 우선."""
        rows = [
            {
                "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
                "area_exclusive": 8400, "source": "building_registry",
            },
            {
                "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
                "area_exclusive": 8450, "source": "public_price",
            },
        ]
        resolved = resolve_conflicts(rows)
        assert resolved["area_exclusive"] == 8450  # public_price wins

    def test_single_row(self):
        """1개 행만 → 충돌 없음, 그대로 반환."""
        row = {
            "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
            "dong": "101", "floor": 15, "area_exclusive": 8400,
            "area_type": "84A", "direction": "S", "source": "public_price",
        }
        resolved = resolve_conflicts([row])
        assert resolved["_conflict_count"] == 0
        assert resolved["dong"] == "101"


class TestRefineUnitMaster:
    def test_no_duplicates(self):
        """중복 없음 → 모든 행 그대로, conflict_count=0."""
        rows = [
            {
                "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
                "dong": "101", "floor": 15, "area_exclusive": 8400,
                "area_type": "84A", "direction": "S", "source": "public_price",
            },
            {
                "canonical_ho_id": "1504", "complex_id": "C1", "ho": "1504",
                "dong": "101", "floor": 15, "area_exclusive": 11500,
                "area_type": "115A", "direction": "S", "source": "building_registry",
            },
        ]
        clean, report = refine_unit_master(rows)
        assert report["total"] == 2
        assert report["clean_count"] == 2
        assert report["conflict_count"] == 0
        assert report["conflict_rate"] == 0.0
        assert len(clean) == 2

    def test_with_duplicates(self):
        """중복 ① — 2개 소스에서 같은 canonical_ho_id → 충돌 해결."""
        rows = [
            {
                "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
                "dong": "101", "floor": 15, "area_exclusive": 8400,
                "area_type": "84A", "direction": "S", "source": "public_price",
            },
            {
                "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
                "dong": "101", "floor": 15, "area_exclusive": 8450,
                "area_type": "84A", "direction": "S", "source": "building_registry",
            },
        ]
        clean, report = refine_unit_master(rows)
        assert report["total"] == 2
        assert report["clean_count"] == 1  # deduplicated
        assert report["conflict_count"] > 0  # area_exclusive 충돌
        assert len(clean) == 1

    def test_conflict_rate_threshold(self):
        """충돌율 > 0.05 → warning True."""
        # 2 rows, 1 conflict group → conflict_rate = 0.5
        rows = [
            {
                "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
                "dong": "101", "floor": 15, "area_exclusive": 8400,
                "area_type": "84A", "direction": "S", "source": "public_price",
            },
            {
                "canonical_ho_id": "1503", "complex_id": "C1", "ho": "1503",
                "dong": "102", "floor": 15, "area_exclusive": 8400,
                "area_type": "84A", "direction": "N", "source": "building_registry",
            },
        ]
        _, report = refine_unit_master(rows)
        assert report["warning"] is True

    def test_empty_rows(self):
        clean, report = refine_unit_master([])
        assert report["total"] == 0
        assert report["clean_count"] == 0
        assert len(clean) == 0
