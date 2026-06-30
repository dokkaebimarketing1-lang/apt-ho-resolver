"""전유부 역추론 배치도 테스트 - 호 끝 2자리=라인, 면적 클러스터링.

테스트 범위:
- extract_line_from_ho: 라인 추출 (4자리, 3자리, 접미사, edge cases)
- cluster_areas_by_line: 라인별 면적 그룹화
- infer_line_type: 면적 패턴으로 A/B/C 타입 클러스터링
- infer_line_direction: 라인별 향 추론 (같은 라인 = 같은 향)
- infer_floorplan: 전체 파이프라인 + 순차 번호 감지 + is_estimate
"""

from __future__ import annotations

from src.floorplan_infer import (
    extract_line_from_ho,
    cluster_areas_by_line,
    infer_line_type,
    infer_line_direction,
    infer_floorplan,
)


# =========================================================================
# extract_line_from_ho - 호 끝 2자리 라인 추출
# =========================================================================


class TestExtractLineFromHo:
    """extract_line_from_ho 라인 추출 규칙."""

    def test_four_digits(self) -> None:
        """Given: 호 "1503"
        When: extract_line_from_ho("1503")
        Then: "03" (끝 2자리)"""
        assert extract_line_from_ho("1503") == "03"

    def test_four_digits_variant(self) -> None:
        """Given: 호 "1504"
        When: extract_line_from_ho("1504")
        Then: "04" (끝 2자리)"""
        assert extract_line_from_ho("1504") == "04"

    def test_three_digits_padded(self) -> None:
        """Given: 호 "503" (3자리)
        When: extract_line_from_ho("503")
        Then: "03" (4자리 정규화 후 끝 2자리)"""
        assert extract_line_from_ho("503") == "03"

    def test_two_digits_padded(self) -> None:
        """Given: 호 "03" (2자리 → 3자리 미만 아님, zfill 후)
        When: extract_line_from_ho("1003")
        Then: "03" (정상 추출)"""
        assert extract_line_from_ho("1003") == "03"

    def test_with_ho_suffix(self) -> None:
        """Given: 호 "1503호"
        When: extract_line_from_ho("1503호")
        Then: "03" (숫자만 추출 후 끝 2자리)"""
        assert extract_line_from_ho("1503호") == "03"

    def test_with_whitespace(self) -> None:
        """Given: 호 "  1503  "
        When: extract_line_from_ho("  1503  ")
        Then: "03" (공백 제거 후 추출)"""
        assert extract_line_from_ho("  1503  ") == "03"

    def test_high_floor(self) -> None:
        """Given: 호 "2501"
        When: extract_line_from_ho("2501")
        Then: "01" (25층 01라인)"""
        assert extract_line_from_ho("2501") == "01"

    def test_line_10_plus(self) -> None:
        """Given: 호 "1510"
        When: extract_line_from_ho("1510")
        Then: "10" (10라인)"""
        assert extract_line_from_ho("1510") == "10"

    # --- edge cases ---

    def test_empty_returns_none(self) -> None:
        """Given: 빈 문자열
        When: extract_line_from_ho("")
        Then: None"""
        assert extract_line_from_ho("") is None

    def test_too_short_returns_none(self) -> None:
        """Given: "15" (2자리, 최소 3자리 미만)
        When: extract_line_from_ho("15")
        Then: None"""
        assert extract_line_from_ho("15") is None

    def test_no_digits_returns_none(self) -> None:
        """Given: "호" (숫자 없음)
        When: extract_line_from_ho("호")
        Then: None"""
        assert extract_line_from_ho("호") is None

    def test_single_digit_returns_none(self) -> None:
        """Given: "3" (1자리)
        When: extract_line_from_ho("3")
        Then: None"""
        assert extract_line_from_ho("3") is None


# =========================================================================
# cluster_areas_by_line - 라인별 면적 그룹화
# =========================================================================


class TestClusterAreasByLine:
    """cluster_areas_by_line 라인별 면적 그룹화."""

    def test_basic_grouping(self) -> None:
        """Given: 3층 x 2라인, 라인별 다른 면적
        When: cluster_areas_by_line(units)
        Then: {"01": [84.0, 84.0, 84.0], "02": [59.0, 59.0, 59.0]}"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "0102", "area_exclusive": 59.0},
            {"ho": "0201", "area_exclusive": 84.0},
            {"ho": "0202", "area_exclusive": 59.0},
            {"ho": "0301", "area_exclusive": 84.0},
            {"ho": "0302", "area_exclusive": 59.0},
        ]
        result = cluster_areas_by_line(units)
        assert result == {
            "01": [84.0, 84.0, 84.0],
            "02": [59.0, 59.0, 59.0],
        }

    def test_single_line(self) -> None:
        """Given: 1개 라인만 존재
        When: cluster_areas_by_line(units)
        Then: {"01": [84.0, 84.0]}"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "0201", "area_exclusive": 84.0},
        ]
        result = cluster_areas_by_line(units)
        assert result == {"01": [84.0, 84.0]}

    def test_empty_list(self) -> None:
        """Given: 빈 리스트
        When: cluster_areas_by_line([])
        Then: {} (빈 딕셔너리)"""
        assert cluster_areas_by_line([]) == {}

    def test_skip_invalid_ho(self) -> None:
        """Given: 일부 호가 너무 짧음
        When: cluster_areas_by_line(units)
        Then: 유효한 호만 그룹화"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "15", "area_exclusive": 59.0},  # too short
            {"ho": "0201", "area_exclusive": 84.0},
        ]
        result = cluster_areas_by_line(units)
        assert result == {"01": [84.0, 84.0]}

    def test_skip_missing_area(self) -> None:
        """Given: 일부 단위에 area_exclusive 누락
        When: cluster_areas_by_line(units)
        Then: 면적 있는 단위만 그룹화"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "0102"},  # no area
            {"ho": "0201", "area_exclusive": 84.0},
        ]
        result = cluster_areas_by_line(units)
        assert result == {"01": [84.0, 84.0]}

    def test_integer_area_converted(self) -> None:
        """Given: area_exclusive 가 정수
        When: cluster_areas_by_line(units)
        Then: float 으로 변환됨"""
        units = [{"ho": "0101", "area_exclusive": 84}]
        result = cluster_areas_by_line(units)
        assert result == {"01": [84.0]}
        assert isinstance(result["01"][0], float)

    def test_three_lines(self) -> None:
        """Given: 3개 라인 (01, 02, 03)
        When: cluster_areas_by_line(units)
        Then: 3개 키 그룹화"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "0102", "area_exclusive": 59.0},
            {"ho": "0103", "area_exclusive": 114.0},
        ]
        result = cluster_areas_by_line(units)
        assert len(result) == 3
        assert "01" in result
        assert "02" in result
        assert "03" in result


# =========================================================================
# infer_line_type - 면적 패턴으로 타입 클러스터링
# =========================================================================


class TestInferLineType:
    """infer_line_type 면적 기반 타입 클러스터링."""

    def test_three_distinct_types(self) -> None:
        """Given: 3개 라인, 각각 다른 면적 (59, 84, 114 m^2)
        When: infer_line_type(units)
        Then: 3개 고유 타입 라벨 (A, B, C) - 면적 작은 순"""
        units = [
            {"ho": "0101", "area_exclusive": 59.0},
            {"ho": "0201", "area_exclusive": 59.0},
            {"ho": "0102", "area_exclusive": 84.0},
            {"ho": "0202", "area_exclusive": 84.0},
            {"ho": "0103", "area_exclusive": 114.0},
            {"ho": "0203", "area_exclusive": 114.0},
        ]
        result = infer_line_type(units)
        assert len(set(result.values())) == 3
        # 59 m^2 = A (가장 작음), 84 m^2 = B, 114 m^2 = C
        assert result["01"] == "A"
        assert result["02"] == "B"
        assert result["03"] == "C"

    def test_two_types(self) -> None:
        """Given: 2개 라인, 다른 면적 (59, 84 m^2)
        When: infer_line_type(units)
        Then: 2개 타입 (A=59, B=84)"""
        units = [
            {"ho": "0101", "area_exclusive": 59.0},
            {"ho": "0201", "area_exclusive": 59.0},
            {"ho": "0102", "area_exclusive": 84.0},
            {"ho": "0202", "area_exclusive": 84.0},
        ]
        result = infer_line_type(units)
        assert len(set(result.values())) == 2
        assert result["01"] == "A"
        assert result["02"] == "B"

    def test_same_area_same_type(self) -> None:
        """Given: 2개 라인, 같은 면적 (84 m^2)
        When: infer_line_type(units)
        Then: 같은 타입 (모두 A)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "0102", "area_exclusive": 84.0},
        ]
        result = infer_line_type(units)
        assert result["01"] == "A"
        assert result["02"] == "A"

    def test_small_variation_same_type(self) -> None:
        """Given: 2개 라인, 면적 차이가 갭 이하 (84.0, 84.3 m^2)
        When: infer_line_type(units)
        Then: 같은 타입 (A)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "0102", "area_exclusive": 84.3},
        ]
        result = infer_line_type(units)
        assert result["01"] == "A"
        assert result["02"] == "A"

    def test_empty_returns_empty(self) -> None:
        """Given: 빈 리스트
        When: infer_line_type([])
        Then: {} (빈 딕셔너리)"""
        assert infer_line_type([]) == {}

    def test_single_line(self) -> None:
        """Given: 1개 라인만
        When: infer_line_type(units)
        Then: {"01": "A"}"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0},
            {"ho": "0201", "area_exclusive": 84.0},
        ]
        result = infer_line_type(units)
        assert result == {"01": "A"}

    def test_labels_ascending_by_area(self) -> None:
        """Given: 3개 라인 (면적 114, 59, 84 - 섞인 순서)
        When: infer_line_type(units)
        Then: 면적 오름차순으로 A, B, C 할당"""
        units = [
            {"ho": "0101", "area_exclusive": 114.0},
            {"ho": "0102", "area_exclusive": 59.0},
            {"ho": "0103", "area_exclusive": 84.0},
        ]
        result = infer_line_type(units)
        assert result["02"] == "A"  # 59 = smallest
        assert result["03"] == "B"  # 84 = middle
        assert result["01"] == "C"  # 114 = largest


# =========================================================================
# infer_line_direction - 라인별 향 추론
# =========================================================================


class TestInferLineDirection:
    """infer_line_direction 라인별 향 매핑."""

    def test_two_lines(self) -> None:
        """Given: 2개 라인 {"01": "A", "02": "B"}
        When: infer_line_direction(line_facts)
        Then: {"01": "S", "02": "N"} (전반부 S, 후반부 N)"""
        line_facts = {"01": "A", "02": "B"}
        result = infer_line_direction(line_facts)
        assert result == {"01": "S", "02": "N"}

    def test_four_lines(self) -> None:
        """Given: 4개 라인 {"01": "A", "02": "A", "03": "B", "04": "B"}
        When: infer_line_direction(line_facts)
        Then: 01=S, 02=S, 03=N, 04=N (전반부 S)"""
        line_facts = {"01": "A", "02": "A", "03": "B", "04": "B"}
        result = infer_line_direction(line_facts)
        assert result["01"] == "S"
        assert result["02"] == "S"
        assert result["03"] == "N"
        assert result["04"] == "N"

    def test_single_line(self) -> None:
        """Given: 1개 라인 {"01": "A"}
        When: infer_line_direction(line_facts)
        Then: {"01": "S"} (단일 라인 = 남향)"""
        result = infer_line_direction({"01": "A"})
        assert result == {"01": "S"}

    def test_three_lines(self) -> None:
        """Given: 3개 라인 {"01": "A", "02": "B", "03": "C"}
        When: infer_line_direction(line_facts)
        Then: 01=S, 02=S, 03=N (ceil(3/2)=2개 남향)"""
        line_facts = {"01": "A", "02": "B", "03": "C"}
        result = infer_line_direction(line_facts)
        assert result["01"] == "S"
        assert result["02"] == "S"
        assert result["03"] == "N"

    def test_empty_returns_empty(self) -> None:
        """Given: 빈 딕셔너리
        When: infer_line_direction({})
        Then: {} (빈 딕셔너리)"""
        assert infer_line_direction({}) == {}

    def test_same_line_same_direction(self) -> None:
        """Given: 여러 라인
        When: infer_line_direction(line_facts)
        Then: 각 라인은 단일 향을 가짐 (같은 라인 = 같은 향)"""
        line_facts = {"01": "A", "02": "B", "03": "A", "04": "B"}
        result = infer_line_direction(line_facts)
        for direction in result.values():
            assert direction in ("S", "N")


# =========================================================================
# infer_floorplan - 전체 역추론 파이프라인
# =========================================================================


class TestInferFloorplan:
    """infer_floorplan 전체 파이프라인."""

    def test_basic_pipeline(self) -> None:
        """Given: 구축 단지 (배치도 없음) - 3층 x 2라인, 59/84 m^2
        When: infer_floorplan(units)
        Then: 라인/타입/향 추론 결과 (is_estimate=True)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0102", "area_exclusive": 59.0, "floor": 1, "dong": "101"},
            {"ho": "0201", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0202", "area_exclusive": 59.0, "floor": 2, "dong": "101"},
            {"ho": "0301", "area_exclusive": 84.0, "floor": 3, "dong": "101"},
            {"ho": "0302", "area_exclusive": 59.0, "floor": 3, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is not None
        assert len(result) == 2  # 2 lines

        # 라인 01 = 84 m^2 = B type, S direction
        r01 = next(r for r in result if r["line"] == "01")
        assert r01["dong"] == "101"
        assert r01["area_type"] == "B"
        assert r01["direction"] == "S"

        # 라인 02 = 59 m^2 = A type, N direction
        r02 = next(r for r in result if r["line"] == "02")
        assert r02["dong"] == "101"
        assert r02["area_type"] == "A"
        assert r02["direction"] == "N"

    def test_is_estimate_true(self) -> None:
        """Given: 정상 단위 데이터
        When: infer_floorplan(units)
        Then: 모든 결과의 is_estimate=True (역추론은 추정)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0201", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is not None
        for entry in result:
            assert entry["is_estimate"] is True

    def test_three_types_pipeline(self) -> None:
        """Given: 3개 타입 (59, 84, 114 m^2) x 2층
        When: infer_floorplan(units)
        Then: 3개 라인, 각각 A/B/C 타입"""
        units = [
            {"ho": "0101", "area_exclusive": 59.0, "floor": 1, "dong": "101"},
            {"ho": "0102", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0103", "area_exclusive": 114.0, "floor": 1, "dong": "101"},
            {"ho": "0201", "area_exclusive": 59.0, "floor": 2, "dong": "101"},
            {"ho": "0202", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0203", "area_exclusive": 114.0, "floor": 2, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is not None
        assert len(result) == 3
        types = {r["line"]: r["area_type"] for r in result}
        assert types["01"] == "A"  # 59
        assert types["02"] == "B"  # 84
        assert types["03"] == "C"  # 114

    def test_multiple_dongs(self) -> None:
        """Given: 2개 동, 각각 2라인
        When: infer_floorplan(units)
        Then: 동별로 독립 추론 (4개 엔트리)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0102", "area_exclusive": 59.0, "floor": 1, "dong": "101"},
            {"ho": "0201", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0202", "area_exclusive": 59.0, "floor": 2, "dong": "101"},
            {"ho": "0101", "area_exclusive": 74.0, "floor": 1, "dong": "102"},
            {"ho": "0102", "area_exclusive": 59.0, "floor": 1, "dong": "102"},
            {"ho": "0201", "area_exclusive": 74.0, "floor": 2, "dong": "102"},
            {"ho": "0202", "area_exclusive": 59.0, "floor": 2, "dong": "102"},
        ]
        result = infer_floorplan(units)
        assert result is not None
        assert len(result) == 4  # 2 dongs x 2 lines

        dong101 = [r for r in result if r["dong"] == "101"]
        dong102 = [r for r in result if r["dong"] == "102"]
        assert len(dong101) == 2
        assert len(dong102) == 2

    def test_output_keys(self) -> None:
        """Given: 정상 단위 데이터
        When: infer_floorplan(units)
        Then: 각 엔트리는 dong, line, area_type, direction, is_estimate 키 포함"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0201", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is not None
        for entry in result:
            assert "dong" in entry
            assert "line" in entry
            assert "area_type" in entry
            assert "direction" in entry
            assert "is_estimate" in entry

    # --- 순차 번호 체계 감지 ---

    def test_sequential_numbering_returns_none(self) -> None:
        """Given: 순차 번호 체계 (1층 01-02, 2층 03-04 - 라인이 안 겹침)
        When: infer_floorplan(units)
        Then: None (역추론 불가)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0102", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0203", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0204", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is None

    def test_sequential_large_complex(self) -> None:
        """Given: 순차 번호 체계 (1층 01-04, 2층 05-08)
        When: infer_floorplan(units)
        Then: None"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0102", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0103", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0104", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0205", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0206", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0207", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0208", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is None

    # --- edge cases ---

    def test_empty_returns_none(self) -> None:
        """Given: 빈 리스트
        When: infer_floorplan([])
        Then: None"""
        assert infer_floorplan([]) is None

    def test_single_floor_not_sequential(self) -> None:
        """Given: 1개 층만 있는 데이터 (순차 감지 불가)
        When: infer_floorplan(units)
        Then: 라인 체계로 간주하여 추론 수행"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0102", "area_exclusive": 59.0, "floor": 1, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is not None
        assert len(result) == 2

    def test_no_valid_lines_returns_none(self) -> None:
        """Given: 모든 호가 너무 짧음
        When: infer_floorplan(units)
        Then: None"""
        units = [
            {"ho": "15", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "15", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is None

    def test_one_dong_sequential_skips_all(self) -> None:
        """Given: 동 101은 라인 체계, 동 102는 순차 체계
        When: infer_floorplan(units)
        Then: None (하나의 동이라도 순차면 전체 스킵)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0201", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "102"},
            {"ho": "0202", "area_exclusive": 84.0, "floor": 2, "dong": "102"},
        ]
        result = infer_floorplan(units)
        assert result is None

    def test_unique_dong_line_entries(self) -> None:
        """Given: 3층 x 2라인 (6 단위)
        When: infer_floorplan(units)
        Then: 2개 엔트리 (라인당 1개, 층 수만큼 중복 안 함)"""
        units = [
            {"ho": "0101", "area_exclusive": 84.0, "floor": 1, "dong": "101"},
            {"ho": "0102", "area_exclusive": 59.0, "floor": 1, "dong": "101"},
            {"ho": "0201", "area_exclusive": 84.0, "floor": 2, "dong": "101"},
            {"ho": "0202", "area_exclusive": 59.0, "floor": 2, "dong": "101"},
            {"ho": "0301", "area_exclusive": 84.0, "floor": 3, "dong": "101"},
            {"ho": "0302", "area_exclusive": 59.0, "floor": 3, "dong": "101"},
        ]
        result = infer_floorplan(units)
        assert result is not None
        assert len(result) == 2  # 2 lines, not 6 units
