"""OnbidChannel 단위 테스트 — mock httpx.Client 기반."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.channels.onbid import OnbidChannel


def _mock_json_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """온비드 API 응답 형태."""
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "정상"},
            "body": {
                "items": {
                    "item": items,
                },
                "numOfRows": 10,
                "pageNo": 1,
                "totalCount": len(items),
            },
        }
    }


def _make_item(goods_id: str = "G2025001",
               goods_nm: str = "서초구 아파트 101동") -> dict[str, Any]:
    return {
        "goodsId": goods_id,
        "goodsNm": goods_nm,
        "sigunguCd": "11650",
        "addr": "서울특별시 서초구",
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
def channel(mock_client: MagicMock) -> OnbidChannel:
    """OnbidChannel with mock client."""
    return OnbidChannel(api_key="test-key", client=mock_client)


class TestOnbidChannel:
    """OnbidChannel collect() 기본 동작."""

    def test_channel_attrs(self) -> None:
        """Given OnbidChannel class Then channel_name/reliability 설정됨"""
        assert OnbidChannel.channel_name == "onbid"
        assert OnbidChannel.reliability == 0.85

    def test_collect_returns_list(self, channel: OnbidChannel,
                                  mock_client: MagicMock) -> None:
        """Given 시군구 코드 When collect Then 결과 리스트 반환"""
        result = channel.collect({"sigungu_cd": "11650"})
        assert len(result) == 1
        assert result[0]["goodsId"] == "G2025001"

    def test_collect_passes_correct_params(self, channel: OnbidChannel,
                                           mock_client: MagicMock) -> None:
        """Given 검색 조건 When collect Then 올바른 params 전달"""
        channel.collect({"sigungu_cd": "11650", "keyword": "래미안"})
        called = mock_client.get.call_args[1]["params"]
        assert called["sigunguCd"] == "11650"
        assert called["keyword"] == "래미안"
        assert called["ServiceKey"] == "test-key"

    def test_empty_response(self, channel: OnbidChannel,
                            mock_client: MagicMock) -> None:
        """Given 빈 응답 When collect Then 빈 리스트"""
        mock_client.get.return_value.json.return_value = _mock_json_response([])
        result = channel.collect({"sigungu_cd": "99999"})
        assert result == []

    def test_single_item_as_dict(self, channel: OnbidChannel,
                                 mock_client: MagicMock) -> None:
        """Given item 이 dict (list 아님) When collect Then 리스트 변환"""
        raw = _mock_json_response([])
        raw["response"]["body"]["items"]["item"] = _make_item("G2025002")
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({"sigungu_cd": "11650"})
        assert len(result) == 1
        assert result[0]["goodsId"] == "G2025002"

    def test_multiple_items(self, channel: OnbidChannel,
                            mock_client: MagicMock) -> None:
        """Given 다중 물건 When collect Then 모두 반환"""
        items = [_make_item("G1", "물건1"), _make_item("G2", "물건2")]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({"sigungu_cd": "11650"})
        assert len(result) == 2

    def test_http_error_fallback(self, channel: OnbidChannel,
                                 mock_client: MagicMock) -> None:
        """Given HTTP 오류 When collect Then 빈 리스트 (재시도 후 폴백)"""
        err_resp = MagicMock(spec=httpx.Response, status_code=500)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=err_resp
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({"sigungu_cd": "11650"})
        assert result == []

    def test_timeout_fallback(self, channel: OnbidChannel,
                              mock_client: MagicMock) -> None:
        """Given 타임아웃 When collect Then 빈 리스트"""
        mock_client.get.side_effect = httpx.TimeoutException(
            "timeout", request=MagicMock()
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({"sigungu_cd": "11650"})
        assert result == []

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Given PUBLIC_DATA_API_KEY 환경변수 When 채널 생성 Then 키 사용"""
        monkeypatch.setenv("PUBLIC_DATA_API_KEY", "env-key-onbid")
        mock_client = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = _mock_json_response([])
        mock_client.get.return_value = resp

        ch = OnbidChannel(client=mock_client)
        ch.collect({"sigungu_cd": "11650"})
        called = mock_client.get.call_args[1]["params"]
        assert called["ServiceKey"] == "env-key-onbid"

    def test_pagination_params(self, channel: OnbidChannel,
                               mock_client: MagicMock) -> None:
        """Given num_of_rows/page_no When collect Then 전달 확인"""
        channel.collect({"sigungu_cd": "11650", "num_of_rows": 50, "page_no": 2})
        called = mock_client.get.call_args[1]["params"]
        assert called["numOfRows"] == 50
        assert called["pageNo"] == 2

    def test_without_optional_params(self, channel: OnbidChannel,
                                     mock_client: MagicMock) -> None:
        """Given 시군구 코드만 When collect Then 필수 params만 전달"""
        channel.collect({"sigungu_cd": "11650"})
        called = mock_client.get.call_args[1]["params"]
        assert "keyword" not in called
        assert called["sigunguCd"] == "11650"
