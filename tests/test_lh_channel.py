"""Tests for LH 공실정보 채널 (src/channels/lh_vacancy.py).

Mock HTTP 기반 테스트 — 실제 apply.lh.or.kr 에 접속하지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import httpx
import pytest

from src.channels.lh_vacancy import (
    LhVacancyChannel,
    LhVacancyData,
    is_lh_rental_complex,
    ChannelCollector,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """Mock httpx.Client — get() 호출을 가로챈다."""
    return MagicMock(spec=httpx.Client)


@pytest.fixture
def channel(mock_client: MagicMock) -> LhVacancyChannel:
    """테스트용 LhVacancyChannel (Mock client 주입)."""
    return LhVacancyChannel(client=mock_client)


def _setup_mock_ok(
    mock_client: MagicMock,
    json_data: dict | list | None = None,
) -> None:
    """Mock 응답을 200 OK 로 설정한다."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = json_data or {}
    mock_client.get.return_value = mock_response


def _setup_mock_error(mock_client: MagicMock, status: int = 500) -> None:
    """Mock 응답을 HTTP 에러로 설정한다."""
    mock_response = MagicMock()
    mock_response.status_code = status
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message=f"HTTP {status}",
        request=MagicMock(),
        response=mock_response,
    )
    mock_client.get.return_value = mock_response


# ===========================================================================
# collect() — 단일 단지 조회
# ===========================================================================


class TestCollect:
    """LhVacancyChannel.collect() 단일 단지 조회 테스트."""

    LH_COMPLEX = ("LH-2026-001", "LH 행복타운 1단지", "서울특별시")

    def test_collect_lh_rental_happy(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given LH 임대 단지 When collect() 호출 Then 공실 데이터 반환."""
        # Given
        _setup_mock_ok(mock_client, {
            "complexId": "LH-2026-001",
            "complexName": "LH 행복타운 1단지",
            "region": "서울특별시",
            "totalUnits": 840,
            "vacantUnits": 23,
        })

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is not None
        assert result.complex_id == "LH-2026-001"
        assert result.complex_name == "LH 행복타운 1단지"
        assert result.region == "서울특별시"
        assert result.total_units == 840
        assert result.vacant_units == 23
        assert result.is_lh_rental is True
        mock_client.get.assert_called_once()

    def test_collect_non_lh_returns_none(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 비LH 단지명 When collect() 호출 Then None (API 호출 없음)."""
        # When
        result = channel.collect(
            "PRIV-456",
            "래미안 프리미어",
            "서울특별시",
        )

        # Then
        assert result is None
        mock_client.get.assert_not_called()

    def test_collect_http_error_returns_none(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given API 500 When collect() Then None 반환."""
        # Given
        _setup_mock_error(mock_client, 500)

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is None
        mock_client.get.assert_called_once()

    def test_collect_http_404_returns_none(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given API 404 When collect() Then None 반환."""
        # Given
        _setup_mock_error(mock_client, 404)

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is None

    def test_collect_invalid_json_returns_none(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 응답 JSON 누락 필드 When collect() Then None."""
        # Given — totalUnits 없음
        _setup_mock_ok(mock_client, {
            "complexId": "LH-2026-001",
            "complexName": "LH 행복타운 1단지",
            "vacantUnits": 23,
        })

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is None

    def test_collect_invalid_type_returns_none(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 응답 vacantUnits 가 문자열 When collect() Then None."""
        # Given
        _setup_mock_ok(mock_client, {
            "complexId": "LH-2026-001",
            "complexName": "LH 행복타운 1단지",
            "totalUnits": 840,
            "vacantUnits": "알수없음",  # int 변환 실패
        })

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is None

    def test_collect_json_decode_error_returns_none(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 응답이 유효 JSON 아님 When collect() Then None."""
        # Given
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.get.return_value = mock_response

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is None

    def test_collect_connection_error_returns_none(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 네트워크 오류 When collect() Then None."""
        # Given
        mock_client.get.side_effect = httpx.ConnectError(
            "Connection refused"
        )

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is None

    def test_collect_data_preserves_collected_at(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 정상 응답 When collect() Then collected_at 이 datetime."""
        # Given
        _setup_mock_ok(mock_client, {
            "complexId": "LH-2026-001",
            "complexName": "LH 행복타운 1단지",
            "region": "서울특별시",
            "totalUnits": 840,
            "vacantUnits": 23,
        })
        before = datetime.now()

        # When
        result = channel.collect(*self.LH_COMPLEX)

        # Then
        assert result is not None
        assert before <= result.collected_at <= datetime.now()


# ===========================================================================
# collect_by_region() — 지역별 조회
# ===========================================================================


class TestCollectByRegion:
    """LhVacancyChannel.collect_by_region() 지역별 조회 테스트."""

    def test_collect_by_region_happy(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 지역 When collect_by_region() Then 복수 단지 목록 반환."""
        # Given
        _setup_mock_ok(mock_client, [
            {
                "complexId": "LH-2026-001",
                "complexName": "LH 행복타운 1단지",
                "region": "서울특별시",
                "totalUnits": 840,
                "vacantUnits": 23,
            },
            {
                "complexId": "LH-2026-002",
                "complexName": "LH 행복타운 2단지",
                "region": "서울특별시",
                "totalUnits": 630,
                "vacantUnits": 5,
            },
        ])

        # When
        results = channel.collect_by_region("서울특별시")

        # Then
        assert len(results) == 2
        assert results[0].complex_name == "LH 행복타운 1단지"
        assert results[0].vacant_units == 23
        assert results[1].complex_name == "LH 행복타운 2단지"
        assert results[1].vacant_units == 5

    def test_collect_by_region_single_item(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 단일 단지 응답 When collect_by_region() Then 리스트 1건."""
        # Given — dict (not list)
        _setup_mock_ok(mock_client, {
            "complexId": "LH-2026-001",
            "complexName": "LH 행복타운 1단지",
            "region": "서울특별시",
            "totalUnits": 840,
            "vacantUnits": 23,
        })

        # When
        results = channel.collect_by_region("서울특별시")

        # Then
        assert len(results) == 1
        assert results[0].vacant_units == 23

    def test_collect_by_region_empty_list(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 빈 리스트 응답 When collect_by_region() Then 빈 리스트."""
        # Given
        _setup_mock_ok(mock_client, [])

        # When
        results = channel.collect_by_region("서울특별시")

        # Then
        assert results == []

    def test_collect_by_region_api_error(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given API 오류 When collect_by_region() Then 빈 리스트."""
        # Given
        _setup_mock_error(mock_client, 500)

        # When
        results = channel.collect_by_region("서울특별시")

        # Then
        assert results == []

    def test_collect_by_region_skips_bad_items(
        self, channel: LhVacancyChannel, mock_client: MagicMock
    ) -> None:
        """Given 일부 항목 필드 누락 When collect_by_region() Then 건너뜀."""
        # Given
        _setup_mock_ok(mock_client, [
            {
                "complexId": "LH-2026-001",
                "complexName": "LH 행복타운 1단지",
                "region": "서울특별시",
                "totalUnits": 840,
                "vacantUnits": 23,
            },
            {
                # totalUnits 누락
                "complexId": "LH-2026-002",
                "complexName": "LH 행복타운 2단지",
                "vacantUnits": 5,
            },
            {
                "complexId": "LH-2026-003",
                "complexName": "LH 행복타운 3단지",
                "region": "서울특별시",
                "totalUnits": 400,
                "vacantUnits": 2,
            },
        ])

        # When
        results = channel.collect_by_region("서울특별시")

        # Then
        assert len(results) == 2  # 가운데 불량 항목 제외
        assert results[0].complex_id == "LH-2026-001"
        assert results[1].complex_id == "LH-2026-003"


# ===========================================================================
# is_lh_rental_complex() — LH 임대 단지 판별
# ===========================================================================


class TestIsLhRentalComplex:
    """is_lh_rental_complex() 단지명 기반 LH 임대 판별 테스트."""

    @pytest.mark.parametrize("name", [
        "LH 행복타운 1단지",
        "LH 국민임대 아파트",
        "LH 영구임대 아파트",
        "LH 공공임대 1단지",
        "lh 소문자 단지",
        "Lh 혼합 단지",
        "엘에이치 임대단지",
        "행복주택 은평",
        "국민임대 수원",
        "영구임대 단지",
        "공공임대 파주",
        "전세임대 단지",
        "매입임대 아파트",
        "통합공공임대 단지",
        "희망타운 서울",
        "LH임대 단지",
        "엘에이치임대 단지",
    ])
    def test_lh_rental_true(self, name: str) -> None:
        """Given 다양한 LH 임대 단지명 When 판별 Then True."""
        assert is_lh_rental_complex(name) is True

    @pytest.mark.parametrize("name", [
        "래미안 프리미어",
        "자이 아파트",
        "힐스테이트",
        "롯데캐슬",
        "e편한세상",
        "",
        "  ",
        "반포자이",
    ])
    def test_lh_rental_false(self, name: str) -> None:
        """Given 비LH 단지명 When 판별 Then False."""
        assert is_lh_rental_complex(name) is False

    def test_lh_rental_lh_in_middle(self) -> None:
        """Given 'LH'가 중간에 When 판별 Then False (접두사만 인정)."""
        assert is_lh_rental_complex("일반LH아파트") is False


# ===========================================================================
# ChannelCollector 프로토콜 준수
# ===========================================================================


class TestChannelProtocol:
    """ChannelCollector 프로토콜 준수 테스트."""

    def test_lh_vacancy_channel_conforms_to_protocol(
        self, channel: LhVacancyChannel
    ) -> None:
        """Given LhVacancyChannel When isinstance(ChannelCollector) Then True."""
        assert isinstance(channel, ChannelCollector)

    def test_channel_attributes(self) -> None:
        """Given LhVacancyChannel 인스턴스 When 속성 확인 Then 올바른 값."""
        ch = LhVacancyChannel()
        assert ch.channel_name == "lh_vacancy"
        assert ch.reliability == 0.9


# ===========================================================================
# LhVacancyData 값 객체
# ===========================================================================


class TestLhVacancyData:
    """LhVacancyData frozen dataclass 테스트."""

    def test_frozen_dataclass(self) -> None:
        """Given LhVacancyData 인스턴스 When 속성 변경 시도 Then FrozenInstanceError."""
        data = LhVacancyData(
            complex_id="LH-001",
            complex_name="LH 테스트",
            region="서울",
            total_units=100,
            vacant_units=5,
        )
        with pytest.raises(AttributeError):
            data.vacant_units = 10  # type: ignore[misc]

    def test_default_is_lh_rental_true(self) -> None:
        """Given 생성 시 is_lh_rental 미지정 When 확인 Then True."""
        data = LhVacancyData(
            complex_id="LH-001",
            complex_name="LH 테스트",
            region="서울",
            total_units=100,
            vacant_units=5,
        )
        assert data.is_lh_rental is True

    def test_default_collected_at_now(self) -> None:
        """Given 생성 시 collected_at 미지정 When 확인 Then datetime."""
        data = LhVacancyData(
            complex_id="LH-001",
            complex_name="LH 테스트",
            region="서울",
            total_units=100,
            vacant_units=5,
        )
        assert isinstance(data.collected_at, datetime)
