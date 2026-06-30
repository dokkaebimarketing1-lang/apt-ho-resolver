"""RtmsChannel 단위 테스트 — mock httpx.Client 기반."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.channels.rtms import RtmsChannel


def _mock_json_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """RTMS API 응답 형태."""
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": {
                    "item": items,
                },
                "numOfRows": 100,
                "pageNo": 1,
                "totalCount": len(items),
            },
        }
    }


def _make_item(
    apt_nm: str = "래미안원베일리",
    apt_dong: str = "101",
    floor: str = "15",
    exclu_use_ar: str = "84.97",
    deal_amount: str = "150,000",
    deal_year: str = "2024",
    deal_month: str = "06",
    deal_day: str = "15",
) -> dict[str, Any]:
    """RTMS API 개별 항목."""
    return {
        "aptNm": apt_nm,
        "aptDong": apt_dong,
        "floor": floor,
        "excluUseAr": exclu_use_ar,
        "dealAmount": deal_amount,
        "dealYear": deal_year,
        "dealMonth": deal_month,
        "dealDay": deal_day,
    }


@pytest.fixture
def mock_client() -> MagicMock:
    """기본 mock httpx.Client."""
    client = MagicMock(spec=httpx.Client)
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = _mock_json_response([_make_item()])
    resp.raise_for_status.return_value = None
    client.get.return_value = resp
    return client


@pytest.fixture
def channel(mock_client: MagicMock) -> RtmsChannel:
    """RtmsChannel with mock client."""
    return RtmsChannel(api_key="test-key", client=mock_client)


class TestRtmsChannelAttrs:
    """RtmsChannel 클래스 속성."""

    def test_channel_attrs(self) -> None:
        """Given RtmsChannel class Then channel_name/reliability 설정됨"""
        assert RtmsChannel.channel_name == "rtms"
        assert RtmsChannel.reliability == 0.8


class TestRtmsChannelCollect:
    """RtmsChannel collect() 기본 동작."""

    def test_collect_returns_list(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 시군구+년월 When collect Then Transaction 리스트 반환"""
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
            "complex_name": "래미안원베일리",
        })
        assert len(result) == 1
        txn = result[0]
        assert txn["complex_id"] == ""
        assert txn["floor"] == 15
        assert txn["area2"] == 84.97
        assert txn["price"] == 150000
        assert txn["contract_date"] == "2024-06-15"
        assert txn["dong"] == "101동"
        assert txn["source_id"] == "rtms_0"

    def test_collect_passes_correct_params(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 검색 조건 When collect Then 올바른 params 전달"""
        channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
            "complex_name": "래미안원베일리",
        })
        called = mock_client.get.call_args[1]["params"]
        assert called["LAWD_CD"] == "11650"
        assert called["DEAL_YMD"] == "202406"
        assert called["serviceKey"] == "test-key"
        assert called["_type"] == "json"

    def test_complex_id_in_result(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given complex_id When collect Then 결과에 complex_id 포함"""
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
            "complex_id": "C12345",
            "complex_name": "래미안원베일리",
        })
        assert result[0]["complex_id"] == "C12345"

    def test_empty_response(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 빈 응답 When collect Then 빈 리스트"""
        mock_client.get.return_value.json.return_value = _mock_json_response([])
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result == []

    def test_single_item_as_dict(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given item 이 dict (list 아님) When collect Then 리스트 변환"""
        raw = _mock_json_response([])
        raw["response"]["body"]["items"]["item"] = _make_item(
            apt_dong="102", floor="10"
        )
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert len(result) == 1
        assert result[0]["floor"] == 10
        assert result[0]["dong"] == "102동"

    def test_multiple_items(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 다중 거래 When collect Then 모두 반환"""
        items = [
            _make_item(apt_dong="101", floor="5", deal_amount="100,000"),
            _make_item(apt_dong="102", floor="10", deal_amount="120,000"),
        ]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert len(result) == 2
        assert result[0]["dong"] == "101동"
        assert result[1]["dong"] == "102동"


class TestRtmsChannelDong:
    """aptDong (동) 필드 처리."""

    def test_blank_dong(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given aptDong 빈값 When collect Then dong = '' (동 정보 없음)"""
        raw = _mock_json_response([
            _make_item(apt_dong=""),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result[0]["dong"] == ""

    def test_blank_dong_whitespace(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given aptDong 공백 When collect Then dong = ''"""
        raw = _mock_json_response([
            _make_item(apt_dong="  "),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result[0]["dong"] == ""

    def test_dong_digits_only(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given aptDong 숫자만 When collect Then 'N동' 보정"""
        raw = _mock_json_response([
            _make_item(apt_dong="108"),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result[0]["dong"] == "108동"

    def test_dong_already_with_suffix(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given aptDong 이미 '동' 접미사 When collect Then 그대로 유지"""
        raw = _mock_json_response([
            _make_item(apt_dong="108동"),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result[0]["dong"] == "108동"

    def test_dong_alphabetic(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given aptDong 문자포함 When collect Then 그대로 유지"""
        raw = _mock_json_response([
            _make_item(apt_dong="라동"),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result[0]["dong"] == "라동"


class TestRtmsChannelFilter:
    """complex_name 필터링."""

    def test_complex_name_filter_match(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given complex_name 일치 항목 When collect Then 해당 항목만"""
        items = [
            _make_item(apt_nm="래미안원베일리", floor="5"),
            _make_item(apt_nm="래미안퍼스티지", floor="10"),
        ]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
            "complex_name": "래미안원베일리",
        })
        assert len(result) == 1
        assert result[0]["floor"] == 5

    def test_complex_name_filter_no_match(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given complex_name 불일치 When collect Then 빈 리스트"""
        items = [
            _make_item(apt_nm="래미안퍼스티지"),
        ]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
            "complex_name": "없는단지",
        })
        assert result == []

    def test_no_complex_name_filter(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given complex_name 없을 때 When collect Then 모든 항목 반환"""
        items = [
            _make_item(apt_nm="래미안원베일리", floor="5"),
            _make_item(apt_nm="래미안퍼스티지", floor="10"),
        ]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert len(result) == 2

    def test_complex_name_filter_whitespace_insensitive(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given complex_name 공백 차이 When collect Then 공백무시 매칭"""
        items = [
            _make_item(apt_nm="래미안 원베일리"),
        ]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
            "complex_name": "래미안원베일리",
        })
        assert len(result) == 1


class TestRtmsChannelErrors:
    """HTTP 오류·타임아웃 처리."""

    def test_http_error_fallback(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given HTTP 오류 When collect Then 빈 리스트 (재시도 후 폴백)"""
        err_resp = MagicMock(spec=httpx.Response, status_code=500)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=err_resp
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({
                "sigungu_cd": "11650",
                "deal_ymd": "202406",
            })
        assert result == []

    def test_timeout_fallback(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 타임아웃 When collect Then 빈 리스트"""
        mock_client.get.side_effect = httpx.TimeoutException(
            "timeout", request=MagicMock()
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({
                "sigungu_cd": "11650",
                "deal_ymd": "202406",
            })
        assert result == []

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Given PUBLIC_DATA_API_KEY 환경변수 When 채널 생성 Then 키 사용"""
        monkeypatch.setenv("PUBLIC_DATA_API_KEY", "env-key-rtms")
        mock_client = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = _mock_json_response([])
        mock_client.get.return_value = resp

        ch = RtmsChannel(client=mock_client)
        ch.collect({"sigungu_cd": "11650", "deal_ymd": "202406"})
        called = mock_client.get.call_args[1]["params"]
        assert called["serviceKey"] == "env-key-rtms"


class TestRtmsChannelEdgeCases:
    """엣지 케이스."""

    def test_missing_sigungu(self, channel: RtmsChannel) -> None:
        """Given sigungu_cd 누락 When collect Then 빈 리스트"""
        result = channel.collect({"deal_ymd": "202406"})
        assert result == []

    def test_missing_deal_ymd(self, channel: RtmsChannel) -> None:
        """Given deal_ymd 누락 When collect Then 빈 리스트"""
        result = channel.collect({"sigungu_cd": "11650"})
        assert result == []

    def test_empty_query(self, channel: RtmsChannel) -> None:
        """Given 빈 query When collect Then 빈 리스트"""
        result = channel.collect({})
        assert result == []

    def test_invalid_data_skip(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 잘못된 데이터(층 음수 등) When collect Then 건너뜀"""
        items = [
            _make_item(floor="invalid", apt_dong="101"),
            _make_item(floor="5", apt_dong="102"),
        ]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert len(result) == 1
        assert result[0]["floor"] == 5

    def test_deal_amount_with_comma(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 거래금액 콤마 포함 When collect Then 정수 변환"""
        raw = _mock_json_response([
            _make_item(deal_amount="12,345,678"),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result[0]["price"] == 12345678

    def test_deal_amount_with_space(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 거래금액 공백 포함 When collect Then 정수 변환"""
        raw = _mock_json_response([
            _make_item(deal_amount="150 000"),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
        })
        assert result[0]["price"] == 150000

    def test_pagination_params(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given num_of_rows/page_no When collect Then params 전달 확인"""
        channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202406",
            "num_of_rows": 50,
            "page_no": 2,
        })
        called = mock_client.get.call_args[1]["params"]
        assert called["numOfRows"] == 50
        assert called["pageNo"] == 2

    def test_contract_date_format(
        self, channel: RtmsChannel, mock_client: MagicMock
    ) -> None:
        """Given 계약일 정보 When collect Then YYYY-MM-DD 형식"""
        raw = _mock_json_response([
            _make_item(deal_year="2024", deal_month="1", deal_day="3"),
        ])
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({
            "sigungu_cd": "11650",
            "deal_ymd": "202401",
        })
        assert result[0]["contract_date"] == "2024-01-03"
