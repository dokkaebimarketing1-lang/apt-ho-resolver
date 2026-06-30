"""RegistryChannel 단위 테스트 — mock httpx.Client 기반."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.channels.registry import (
    RegistryChannel,
    _ADDRESS_SIMILARITY_MIN_SCORE,
)


# ------------------------------------------------------------------
# 헬퍼 — mock 응답
# ------------------------------------------------------------------

def _mock_registry_response(
    buildings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """등기부등본 mock 응답 생성.

    Args:
        buildings: 건물표시 목록. 기본 1건(101동 1503호, 서초구).

    Returns:
        등기부 JSON 응답 dict.
    """
    if buildings is None:
        buildings = [
            {
                "dong": "101",
                "ho": "1503",
                "owner_address": "서울특별시 서초구 서초동 1234",
            },
        ]
    result: dict[str, Any] = {
        "building_description": buildings,
        "owner_info": [],
    }
    # owner_info 는 첫 번째 항목에서만 참조 (가변 입력 보호)
    if isinstance(buildings, list) and buildings and "owner_address" in buildings[0]:
        result["owner_info"] = [
            {"name": "홍길동", "address": buildings[0]["owner_address"]},
        ]
    return result


@pytest.fixture
def mock_client() -> MagicMock:
    """기본 mock httpx.Client — 1건 등기부 응답."""
    client = MagicMock(spec=httpx.Client)
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = _mock_registry_response()
    resp.raise_for_status.return_value = None
    client.get.return_value = resp
    return client


@pytest.fixture
def channel(mock_client: MagicMock) -> RegistryChannel:
    """RegistryChannel with mock client."""
    return RegistryChannel(api_key="test-key", client=mock_client)


# ------------------------------------------------------------------
# 채널 기본 속성
# ------------------------------------------------------------------

class TestRegistryChannelAttrs:
    """RegistryChannel 클래스 속성 검증."""

    def test_channel_name(self) -> None:
        """Given RegistryChannel class Then channel_name='registry'"""
        assert RegistryChannel.channel_name == "registry"

    def test_reliability(self) -> None:
        """Given RegistryChannel class Then reliability=0.98"""
        assert RegistryChannel.reliability == 0.98

    def test_channel_collector_protocol(self) -> None:
        """Given RegistryChannel instance Then ChannelCollector Protocol 만족"""
        from src.channels.base import ChannelCollector
        assert isinstance(RegistryChannel(api_key="k"), ChannelCollector)


# ------------------------------------------------------------------
# collect() 기본 동작
# ------------------------------------------------------------------

class TestCollect:
    """RegistryChannel collect() 기본 동작."""

    def test_collect_returns_list(self, channel: RegistryChannel) -> None:
        """Given 정상 query When collect Then 결과 리스트 반환"""
        result = channel.collect({
            "dong": "101", "ho": "1503", "complex_id": "C001",
        })
        assert isinstance(result, list)
        assert len(result) == 1

    def test_collect_parsed_fields(self, channel: RegistryChannel) -> None:
        """Given 등기부 응답 When collect Then dong/ho/owner_address 추출"""
        result = channel.collect({
            "dong": "101", "ho": "1503", "complex_id": "C001",
        })
        item = result[0]
        assert item["dong"] == "101"
        assert item["ho"] == "1503"
        assert "owner_address" in item
        assert "is_non_resident" in item

    def test_collect_passes_correct_params(self, channel: RegistryChannel,
                                           mock_client: MagicMock) -> None:
        """Given query When collect Then 올바른 params 전달"""
        channel.collect({
            "dong": "202", "ho": "801", "complex_id": "C002",
        })
        called = mock_client.get.call_args[1]["params"]
        assert called["dong"] == "202"
        assert called["ho"] == "801"
        assert called["complex_id"] == "C002"
        assert called["serviceKey"] == "test-key"

    def test_missing_dong_returns_empty(self, channel: RegistryChannel,
                                        mock_client: MagicMock) -> None:
        """Given dong 없을 때 When collect Then 빈 리스트 (API 호출 안 함)"""
        result = channel.collect({"ho": "1503"})
        assert result == []
        mock_client.get.assert_not_called()

    def test_missing_ho_returns_empty(self, channel: RegistryChannel,
                                      mock_client: MagicMock) -> None:
        """Given ho 없을 때 When collect Then 빈 리스트"""
        result = channel.collect({"dong": "101"})
        assert result == []
        mock_client.get.assert_not_called()

    def test_empty_dong_and_ho(self, channel: RegistryChannel) -> None:
        """Given dong/ho 둘 다 빈 문자열 When collect Then 빈 리스트"""
        result = channel.collect({"dong": "", "ho": ""})
        assert result == []

    def test_collect_with_complex_address(self, channel: RegistryChannel,
                                          mock_client: MagicMock) -> None:
        """Given complex_address 포함 When collect Then 전달 확인"""
        channel.collect({
            "dong": "101", "ho": "1503",
            "complex_address": "서울 서초구 서초동",
        })
        # API 호출 시 complex_address는 params에 포함되지 않음 (내부용)
        called = mock_client.get.call_args[1]["params"]
        assert "complex_address" not in called


# ------------------------------------------------------------------
# _parse_registry_response
# ------------------------------------------------------------------

class TestParseRegistryResponse:
    """등기부 응답 파싱."""

    def test_parse_single_building(self) -> None:
        """Given 단일 건물표시 When parse Then 1건 리스트"""
        data = _mock_registry_response([
            {"dong": "101", "ho": "1503", "owner_address": "서울 서초구"},
        ])
        result = RegistryChannel._parse_registry_response(data, "")
        assert len(result) == 1
        assert result[0]["dong"] == "101"
        assert result[0]["ho"] == "1503"

    def test_parse_multiple_buildings(self) -> None:
        """Given 복수 건물표시 When parse Then 각각 파싱"""
        data = _mock_registry_response([
            {"dong": "101", "ho": "1503", "owner_address": "주소1"},
            {"dong": "102", "ho": "201", "owner_address": "주소2"},
        ])
        result = RegistryChannel._parse_registry_response(data, "")
        assert len(result) == 2
        assert result[0]["dong"] == "101"
        assert result[1]["dong"] == "102"

    def test_parse_empty_buildings(self) -> None:
        """Given 건물표시 없음 When parse Then 빈 리스트"""
        data = _mock_registry_response([])
        result = RegistryChannel._parse_registry_response(data, "")
        assert result == []

    def test_parse_missing_buildings_key(self) -> None:
        """Given building_description 키 없음 When parse Then 빈 리스트"""
        result = RegistryChannel._parse_registry_response({}, "")
        assert result == []

    def test_parse_dict_buildings(self) -> None:
        """Given building_description 가 dict When parse Then 리스트로 래핑"""
        data = _mock_registry_response({
            "dong": "101", "ho": "1503", "owner_address": "서울",
        })
        result = RegistryChannel._parse_registry_response(data, "")
        assert len(result) == 1
        assert result[0]["dong"] == "101"

    def test_parse_partial_missing_fields(self) -> None:
        """Given 일부 필드 누락 When parse Then 빈 문자열 처리"""
        data = _mock_registry_response([
            {"dong": "101"},  # ho, owner_address 없음
        ])
        result = RegistryChannel._parse_registry_response(data, "")
        assert result[0]["dong"] == "101"
        assert result[0]["ho"] == ""

    def test_parse_none_values(self) -> None:
        """Given 필드 값이 None When parse Then 빈 문자열 처리"""
        data = _mock_registry_response([
            {"dong": None, "ho": None, "owner_address": None},
        ])
        result = RegistryChannel._parse_registry_response(data, "")
        assert result[0]["dong"] == ""
        assert result[0]["ho"] == ""
        assert result[0]["owner_address"] == ""


# ------------------------------------------------------------------
# _check_non_resident
# ------------------------------------------------------------------

class TestCheckNonResident:
    """소유자 미거주 신호 판별."""

    def test_exact_match(self) -> None:
        """Given 주소 완전 일치 When check Then False (거주 중)"""
        result = RegistryChannel._check_non_resident(
            "서울 서초구 서초동 1234", "서울 서초구 서초동 1234",
        )
        assert result is False

    def test_complex_in_owner_address(self) -> None:
        """Given 단지주소가 소유자주소에 포함 When check Then False"""
        result = RegistryChannel._check_non_resident(
            "서울특별시 서초구 서초동 1234-5 101동 1503호",
            "서울특별시 서초구 서초동 1234",
        )
        assert result is False

    def test_completely_different(self) -> None:
        """Given 완전히 다른 주소 When check Then True (미거주)"""
        result = RegistryChannel._check_non_resident(
            "부산광역시 해운대구 우동 123",
            "서울특별시 서초구 서초동 1234",
        )
        assert result is True

    def test_empty_owner_address(self) -> None:
        """Given 소유자주소 비어있음 When check Then False"""
        result = RegistryChannel._check_non_resident(
            "", "서울 서초구 서초동 1234",
        )
        assert result is False

    def test_empty_complex_address(self) -> None:
        """Given 단지주소 비어있음 When check Then False"""
        result = RegistryChannel._check_non_resident(
            "서울 서초구 서초동 1234", "",
        )
        assert result is False

    def test_both_empty(self) -> None:
        """Given 둘 다 비어있음 When check Then False"""
        result = RegistryChannel._check_non_resident("", "")
        assert result is False

    def test_similar_address_below_threshold(self) -> None:
        """Given 유사도 낮지만 임계값 미만 When check Then True"""
        result = RegistryChannel._check_non_resident(
            "서울 강남구 역삼동 567", "인천광역시 부평구 산곡동 89",
        )
        assert result is True

    def test_similar_address_above_threshold(self) -> None:
        """Given 유사도가 임계값 이상 When check Then False"""
        # "서울 서초구 서초동 1234" vs "서울 서초구 서초동 5678"
        # 공통 접두사: "서울 서초구 서초동 " = 12자
        # max_len: 20 vs 20 → score = 12/20 = 0.6
        result = RegistryChannel._check_non_resident(
            "서울 서초구 서초동 1234",
            "서울 서초구 서초동 5678",
        )
        # 0.6 >= 0.6 (임계값) → 거주 가능성 있음
        assert result is False


# ------------------------------------------------------------------
# _address_similarity
# ------------------------------------------------------------------

class TestAddressSimilarity:
    """주소 유사도 계산."""

    def test_identical(self) -> None:
        """Given 동일 주소 When similarity Then 1.0"""
        score = RegistryChannel._address_similarity(
            "서울 서초구 서초동 1234", "서울 서초구 서초동 1234",
        )
        assert score == 1.0

    def test_completely_different(self) -> None:
        """Given 완전히 다른 주소 When similarity Then 0.0"""
        score = RegistryChannel._address_similarity("서울", "부산")
        # "서" vs "부": common=0
        assert score == 0.0

    def test_partial_match(self) -> None:
        """Given 부분 일치 When similarity Then 0.0~1.0 사이"""
        score = RegistryChannel._address_similarity(
            "서울 서초구 서초동 1234",
            "서울 서초구 서초동 5678",
        )
        # 공통 접두사 "서울 서초구 서초동 " = 12자
        # max_len = 20
        assert 0.5 <= score <= 1.0

    def test_whitespace_normalization(self) -> None:
        """Given 공백 차이 When similarity Then 정규화되어 동일"""
        score = RegistryChannel._address_similarity(
            "서울   서초구  서초동", "서울 서초구 서초동",
        )
        # 정규화 후 "서울 서초구 서초동" vs "서울 서초구 서초동"
        # score = 14/14 = 1.0
        assert score == 1.0

    def test_first_empty(self) -> None:
        """Given 첫 번째 주소 빈 문자열 When similarity Then 0.0"""
        score = RegistryChannel._address_similarity("", "서울 서초구")
        assert score == 0.0

    def test_both_empty(self) -> None:
        """Given 둘 다 빈 문자열 When similarity Then 0.0"""
        score = RegistryChannel._address_similarity("", "")
        assert score == 0.0

    def test_one_contains_other(self) -> None:
        """Given 한 주소가 다른 주소 포함 When similarity Then < 1.0"""
        score = RegistryChannel._address_similarity(
            "서울 서초구", "서울 서초구 서초동 1234",
        )
        # "서울 서초구" vs "서울 서초구 서초동 1234"
        # common = 8 (서울 서초구)
        # max_len = 16
        assert 0.0 < score < 1.0


# ------------------------------------------------------------------
# 에러 처리
# ------------------------------------------------------------------

class TestRegistryErrorHandling:
    """HTTP 에러/타임아웃 처리."""

    def test_http_error_fallback(self, mock_client: MagicMock) -> None:
        """Given HTTP 500 When collect Then 빈 리스트 (재시도 후 폴백)"""
        ch = RegistryChannel(api_key="key", client=mock_client)
        err_resp = MagicMock(spec=httpx.Response, status_code=500)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=err_resp,
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = ch.collect({"dong": "101", "ho": "1503"})
        assert result == []

    def test_timeout_fallback(self, mock_client: MagicMock) -> None:
        """Given 타임아웃 When collect Then 빈 리스트"""
        ch = RegistryChannel(api_key="key", client=mock_client)
        mock_client.get.side_effect = httpx.TimeoutException(
            "timeout", request=MagicMock(),
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = ch.collect({"dong": "101", "ho": "1503"})
        assert result == []

    def test_connect_error_fallback(self, mock_client: MagicMock) -> None:
        """Given 연결 오류 When collect Then 빈 리스트"""
        ch = RegistryChannel(api_key="key", client=mock_client)
        mock_client.get.side_effect = httpx.ConnectError(
            "connection refused",
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = ch.collect({"dong": "101", "ho": "1503"})
        assert result == []


# ------------------------------------------------------------------
# collect() 통합 — is_non_resident
# ------------------------------------------------------------------

class TestCollectNonResident:
    """collect() 시 is_non_resident 플래그 검증."""

    def test_non_resident_true(self, mock_client: MagicMock) -> None:
        """Given 소유자 주소가 단지와 다를 때 When collect Then is_non_resident=True"""
        resp_data = _mock_registry_response([
            {
                "dong": "101",
                "ho": "1503",
                "owner_address": "부산광역시 해운대구 우동 123",
            },
        ])
        mock_client.get.return_value.json.return_value = resp_data
        ch = RegistryChannel(api_key="key", client=mock_client)
        result = ch.collect({
            "dong": "101", "ho": "1503",
            "complex_address": "서울특별시 서초구 서초동 1234",
        })
        assert result[0]["is_non_resident"] is True

    def test_non_resident_false(self, mock_client: MagicMock) -> None:
        """Given 소유자 주소가 단지와 같을 때 When collect Then is_non_resident=False"""
        resp_data = _mock_registry_response([
            {
                "dong": "101",
                "ho": "1503",
                "owner_address": "서울 서초구 서초동 1234",
            },
        ])
        mock_client.get.return_value.json.return_value = resp_data
        ch = RegistryChannel(api_key="key", client=mock_client)
        result = ch.collect({
            "dong": "101", "ho": "1503",
            "complex_address": "서울 서초구 서초동 1234",
        })
        assert result[0]["is_non_resident"] is False

    def test_non_resident_within_complex(self, mock_client: MagicMock) -> None:
        """Given 소유자주소에 단지주소 포함 When collect Then is_non_resident=False"""
        resp_data = _mock_registry_response([
            {
                "dong": "101",
                "ho": "1503",
                "owner_address": "서울 서초구 서초동 1234 101동",
            },
        ])
        mock_client.get.return_value.json.return_value = resp_data
        ch = RegistryChannel(api_key="key", client=mock_client)
        result = ch.collect({
            "dong": "101", "ho": "1503",
            "complex_address": "서울 서초구 서초동 1234",
        })
        assert result[0]["is_non_resident"] is False


# ------------------------------------------------------------------
# 상수
# ------------------------------------------------------------------

class TestConstants:
    """모듈 상수 검증."""

    def test_similarity_min_score_value(self) -> None:
        """Given _ADDRESS_SIMILARITY_MIN_SCORE Then 0.6"""
        assert _ADDRESS_SIMILARITY_MIN_SCORE == 0.6
