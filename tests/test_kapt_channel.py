"""KaptChannel 단위 테스트 — mock httpx.Client 기반."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.channels.kapt import KaptChannel


def _mock_json_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """K-apt API 응답 형태."""
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
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


def _make_item(kapt_code: str = "A10022877",
               kapt_name: str = "래미안퍼스티지",
               sigungu: str = "11680") -> dict[str, Any]:
    return {
        "kaptCode": kapt_code,
        "kaptName": kapt_name,
        "sigunguCd": sigungu,
        "bjdongCd": "10300",
        "address": "서울특별시 강남구",
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
def channel(mock_client: MagicMock) -> KaptChannel:
    """KaptChannel with mock client."""
    return KaptChannel(api_key="test-key", client=mock_client)


class TestKaptChannel:
    """KaptChannel collect() 기본 동작."""

    def test_channel_attrs(self) -> None:
        """Given KaptChannel class Then channel_name/reliability 설정됨"""
        assert KaptChannel.channel_name == "kapt"
        assert KaptChannel.reliability == 0.9

    def test_collect_returns_list(self, channel: KaptChannel,
                                  mock_client: MagicMock) -> None:
        """Given 시군구 코드 When collect Then 결과 리스트 반환"""
        result = channel.collect({"sigungu_cd": "11680"})
        assert len(result) == 1
        assert result[0]["kaptCode"] == "A10022877"

    def test_collect_passes_correct_params(self, channel: KaptChannel,
                                           mock_client: MagicMock) -> None:
        """Given 검색 조건 When collect Then 올바른 params 전달"""
        channel.collect({"sigungu_cd": "11680", "bjdong_cd": "10300",
                         "complex_name": "래미안"})
        called = mock_client.get.call_args[1]["params"]
        assert called["sigunguCd"] == "11680"
        assert called["bjdongCd"] == "10300"
        assert called["searchAptNm"] == "래미안"
        assert called["serviceKey"] == "test-key"

    def test_empty_response(self, channel: KaptChannel,
                            mock_client: MagicMock) -> None:
        """Given 빈 응답 When collect Then 빈 리스트"""
        mock_client.get.return_value.json.return_value = _mock_json_response([])
        result = channel.collect({"sigungu_cd": "99999"})
        assert result == []

    def test_single_item_as_dict(self, channel: KaptChannel,
                                 mock_client: MagicMock) -> None:
        """Given item 이 dict (list 아님) When collect Then 리스트 변환"""
        raw = _mock_json_response([])
        raw["response"]["body"]["items"]["item"] = _make_item("A10000000")
        mock_client.get.return_value.json.return_value = raw
        result = channel.collect({"sigungu_cd": "11680"})
        assert len(result) == 1
        assert result[0]["kaptCode"] == "A10000000"

    def test_multiple_items(self, channel: KaptChannel,
                            mock_client: MagicMock) -> None:
        """Given 다중 단지 When collect Then 모두 반환"""
        items = [
            _make_item("A10000001", "단지1"),
            _make_item("A10000002", "단지2"),
        ]
        mock_client.get.return_value.json.return_value = _mock_json_response(items)
        result = channel.collect({"sigungu_cd": "11680"})
        assert len(result) == 2

    def test_http_error_fallback(self, channel: KaptChannel,
                                 mock_client: MagicMock) -> None:
        """Given HTTP 오류 When collect Then 빈 리스트 (재시도 후 폴백)"""
        err_resp = MagicMock(spec=httpx.Response, status_code=500)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=err_resp
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({"sigungu_cd": "11680"})
        assert result == []

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Given PUBLIC_DATA_API_KEY 환경변수 When 채널 생성 Then 키 사용"""
        monkeypatch.setenv("PUBLIC_DATA_API_KEY", "env-key-kapt")
        mock_client = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = _mock_json_response([])
        mock_client.get.return_value = resp

        ch = KaptChannel(client=mock_client)
        ch.collect({"sigungu_cd": "11680"})
        called = mock_client.get.call_args[1]["params"]
        assert called["serviceKey"] == "env-key-kapt"

    def test_pagination_params(self, channel: KaptChannel,
                               mock_client: MagicMock) -> None:
        """Given num_of_rows/page_no When collect Then 전달 확인"""
        channel.collect({"sigungu_cd": "11680", "num_of_rows": 50, "page_no": 2})
        called = mock_client.get.call_args[1]["params"]
        assert called["numOfRows"] == 50
        assert called["pageNo"] == 2
