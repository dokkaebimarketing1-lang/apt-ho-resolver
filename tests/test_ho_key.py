"""호 키 정합 모듈 테스트 — 4개 소스 정규화 + canonical 결정.

테스트 범위:
- normalize_ho: 4개 소스별 정규화 규칙 (일반, 복합 표기, 접미사, 앞채우기)
- normalize_dong: 동명 정규화 (101동 → 101)
- resolve_canonical: 주상복합/임대혼합/재건축 시나리오 포함 교차 검증
- Edge cases: 빈 입력, 정규화 불가, 다중 불일치
"""

from __future__ import annotations

from src.ho_key import (
    normalize_dong,
    normalize_ho,
    resolve_canonical,
    SOURCE_PRIORITY,
)

# =========================================================================
# normalize_ho — 4개 소스 정규화
# =========================================================================


class TestNormalizeHo:
    """normalize_ho 기본 정규화 규칙."""

    # --- 기본 정규화 (공시가격) ---
    def test_public_price_basic(self) -> None:
        """Given: 공시가격 호 "1503"
        When: normalize_ho("1503", "public_price")
        Then: "1503" (변환 없음)"""
        assert normalize_ho("1503", "public_price") == "1503"

    def test_public_price_pad(self) -> None:
        """Given: 공시가격 호 "503"
        When: normalize_ho("503", "public_price")
        Then: "0503" (앞채우기 4자리)"""
        assert normalize_ho("503", "public_price") == "0503"

    def test_public_price_single_digit(self) -> None:
        """Given: 공시가격 호 "3"
        When: normalize_ho("3", "public_price")
        Then: "0003" (앞채우기)"""
        assert normalize_ho("3", "public_price") == "0003"

    # --- 등기 정규화 ---
    def test_registry_ho_suffix(self) -> None:
        """Given: 등기 호 "1503호"
        When: normalize_ho("1503호", "registry")
        Then: "1503" (접미사 "호" 제거)"""
        assert normalize_ho("1503호", "registry") == "1503"

    def test_registry_ho_suffix_pad(self) -> None:
        """Given: 등기 호 "503호"
        When: normalize_ho("503호", "registry")
        Then: "0503" (접미사 제거 + 앞채우기)"""
        assert normalize_ho("503호", "registry") == "0503"

    # --- 대장 전유부 정규화 ---
    def test_building_registry_basic(self) -> None:
        """Given: 대장 호 "1503"
        When: normalize_ho("1503", "building_registry")
        Then: "1503" (변환 없음)"""
        assert normalize_ho("1503", "building_registry") == "1503"

    def test_building_registry_complex(self) -> None:
        """Given: 대장 호 "15-0301"
        When: normalize_ho("15-0301", "building_registry")
        Then: "1503" (복합 표기 분해: 층(15) + 라인(03))"""
        assert normalize_ho("15-0301", "building_registry") == "1503"

    def test_building_registry_complex_variant(self) -> None:
        """Given: 대장 호 "15-0401"
        When: normalize_ho("15-0401", "building_registry")
        Then: "1504" (복합 표기 분해: 층(15) + 라인(04))"""
        assert normalize_ho("15-0401", "building_registry") == "1504"

    def test_building_registry_complex_12f(self) -> None:
        """Given: 대장 호 "12-0201"
        When: normalize_ho("12-0201", "building_registry")
        Then: "1202" (복합 표기 분해: 12층 + 라인 02)"""
        assert normalize_ho("12-0201", "building_registry") == "1202"

    # --- 분양 정규화 ---
    def test_sale_ho_suffix(self) -> None:
        """Given: 분양 호 "1503호"
        When: normalize_ho("1503호", "sale")
        Then: "1503" (접미사 제거)"""
        assert normalize_ho("1503호", "sale") == "1503"

    def test_sale_dong_prefix_ho_suffix(self) -> None:
        """Given: 분양 호 "동 1503호"
        When: normalize_ho("동 1503호", "sale")
        Then: "1503" (동 접두사 + 호 접미사 제거)"""
        assert normalize_ho("동 1503호", "sale") == "1503"

    def test_sale_dong_prefix_no_ho(self) -> None:
        """Given: 분양 호 "동1503"
        When: normalize_ho("동1503", "sale")
        Then: "1503" (동 접두사 제거)"""
        assert normalize_ho("동1503", "sale") == "1503"

    # --- 공백/특수문자 처리 ---
    def test_whitespace_trim(self) -> None:
        """Given: "  1503호  "
        When: normalize_ho("  1503호  ", "sale")
        Then: "1503" (공백 제거)"""
        assert normalize_ho("  1503호  ", "sale") == "1503"

    def test_hyphen_other_source(self) -> None:
        """Given: "15-0301" with source="public_price"
        When: normalize_ho("15-0301", "public_price")
        Then: "150301" (building_registry 외는 일반 숫자추출)"""
        assert normalize_ho("15-0301", "public_price") == "150301"

    # --- 오류 케이스 ---
    def test_empty_raises(self) -> None:
        """Given: 빈 문자열
        When: normalize_ho("", "public_price")
        Then: ValueError"""
        import pytest
        with pytest.raises(ValueError, match="빈 호 표기"):
            normalize_ho("", "public_price")

    def test_blank_raises(self) -> None:
        """Given: 공백 문자열
        When: normalize_ho("   ", "registry")
        Then: ValueError"""
        import pytest
        with pytest.raises(ValueError, match="빈 호 표기"):
            normalize_ho("   ", "registry")

    def test_no_digits_raises(self) -> None:
        """Given: "호" (숫자 없음)
        When: normalize_ho("호", "registry")
        Then: ValueError"""
        import pytest
        with pytest.raises(ValueError, match="정규화 후 빈 결과"):
            normalize_ho("호", "registry")


# =========================================================================
# normalize_dong — 동명 정규화
# =========================================================================


class TestNormalizeDong:
    """normalize_dong 동 표기 정규화."""

    def test_dong_suffix(self) -> None:
        """Given: "101동"
        When: normalize_dong("101동", "public_price")
        Then: "101" (접미사 제거)"""
        assert normalize_dong("101동", "public_price") == "101"

    def test_dong_no_suffix(self) -> None:
        """Given: "101"
        When: normalize_dong("101", "registry")
        Then: "101" (변환 없음)"""
        assert normalize_dong("101", "registry") == "101"

    def test_dong_ra_dong(self) -> None:
        """Given: "라동"
        When: normalize_dong("라동", "public_price")
        Then: ValueError (한글만 있음)"""
        import pytest
        with pytest.raises(ValueError, match="동 정규화 후 빈 결과"):
            normalize_dong("라동", "public_price")

    def test_dong_whitespace(self) -> None:
        """Given: "  101동  "
        When: normalize_dong("  101동  ", "sale")
        Then: "101" (공백 + 접미사 제거)"""
        assert normalize_dong("  101동  ", "sale") == "101"

    def test_dong_empty_raises(self) -> None:
        """Given: 빈 문자열
        When: normalize_dong("", "public_price")
        Then: ValueError"""
        import pytest
        with pytest.raises(ValueError, match="빈 동 표기"):
            normalize_dong("", "public_price")


# =========================================================================
# resolve_canonical — 4개 소스 교차 검증 + 충돌 해결
# =========================================================================


class TestResolveCanonical:
    """resolve_canonical — 4개 소스 교차 검증 및 우선순위 충돌 해결."""

    def test_all_sources_agree(self) -> None:
        """Given: 4개 소스 모두 동일 (동=101, 호=1503)
        When: resolve_canonical(...)
        Then: ("101", "1503")"""
        result = resolve_canonical({
            "registry": ("101", "1503"),
            "public_price": ("101", "1503"),
            "building_registry": ("101", "15-0301"),
            "sale": ("101", "1503호"),
        })
        assert result == ("101", "1503")

    def test_mixed_representation_agrees(self) -> None:
        """Given: 4개 소스 표기만 다르고 내용은 같음
        When: resolve_canonical(...)
        Then: ("101", "1503")"""
        result = resolve_canonical({
            "registry": ("101동", "1503호"),
            "public_price": ("101동", "1503"),
            "building_registry": ("101동", "15-0301"),
            "sale": ("101", "1503호"),
        })
        assert result == ("101", "1503")

    def test_registry_priority_over_public_price(self) -> None:
        """Given: 동이 다른 경우 — registry("101", "1503"),
            public_price("102", "1503")
        When: resolve_canonical(...)
        Then: ("101", "1503") (등기 우선)"""
        result = resolve_canonical({
            "registry": ("101", "1503"),
            "public_price": ("102", "1503"),
        })
        assert result == ("101", "1503")

    def test_registry_priority_over_public_price_dong_diff(self) -> None:
        """Given: 동이 다른 경우 (재건축) — registry("103", "1503"),
            public_price("101", "1503")
        When: resolve_canonical(...)
        Then: ("103", "1503") (등기 우선)"""
        result = resolve_canonical({
            "registry": ("103", "1503"),
            "public_price": ("101", "1503"),
        })
        assert result == ("103", "1503")

    def test_public_price_priority_over_building_registry(self) -> None:
        """Given: 호가 다른 경우 — public_price("101", "1503"),
            building_registry("101", "1603")
        When: resolve_canonical(...)
        Then: ("101", "1503") (공시 > 대장)"""
        result = resolve_canonical({
            "public_price": ("101", "1503"),
            "building_registry": ("101", "1603"),
        })
        assert result == ("101", "1503")

    def test_single_source(self) -> None:
        """Given: 단일 소스만 있을 때
        When: resolve_canonical({"sale": ("101", "1503호")})
        Then: ("101", "1503")"""
        result = resolve_canonical({"sale": ("101", "1503호")})
        assert result == ("101", "1503")

    # --- 정합 불가 케이스 ---
    def test_empty_dict_returns_none(self) -> None:
        """Given: 빈 딕셔너리
        When: resolve_canonical({})
        Then: None"""
        assert resolve_canonical({}) is None

    def test_all_sources_fail_normalization(self) -> None:
        """Given: 모든 소스 정규화 실패
        When: resolve_canonical({"public_price": ("동", "호")})
        Then: None"""
        result = resolve_canonical({"public_price": ("동", "호")})
        assert result is None

    def test_partial_fail_normalization(self) -> None:
        """Given: 일부 소스만 정규화 실패
        When: resolve_canonical(
            {"registry": ("101", "1503"),
             "sale": ("동", "호")})
        Then: ("101", "1503") (정규화 성공한 소스 사용)"""
        result = resolve_canonical({
            "registry": ("101", "1503"),
            "sale": ("동", "호"),  # 정규화 실패
        })
        assert result == ("101", "1503")


# =========================================================================
# SOURCE_PRIORITY
# =========================================================================


class TestSourcePriority:
    """SOURCE_PRIORITY 상수 검증."""

    def test_priority_order(self) -> None:
        """Given: SOURCE_PRIORITY
        Then: registry > public_price > building_registry > sale 순서"""
        assert SOURCE_PRIORITY == (
            "registry",
            "public_price",
            "building_registry",
            "sale",
        )

    def test_priority_all_four(self) -> None:
        """Given: SOURCE_PRIORITY
        Then: 4개 소스 모두 존재"""
        assert len(SOURCE_PRIORITY) == 4
        assert "registry" in SOURCE_PRIORITY
        assert "public_price" in SOURCE_PRIORITY
        assert "building_registry" in SOURCE_PRIORITY
        assert "sale" in SOURCE_PRIORITY
