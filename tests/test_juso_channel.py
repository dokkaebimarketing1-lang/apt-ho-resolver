"""JusoChannel 단위 테스트 — mock httpx.Client 기반."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.channels.juso import JusoChannel


def _mock_json_response(juso_items: list[dict[str, Any]]) -> dict[str, Any]:
    """도로명주소 API 응답 형태."""
    return {
        "results": {
            "common": {"totalCount": str(len(juso_items)), "currentPage": "1", "countPerPage": "100"},
            "juso": juso_items,
        }
    }


@pytest.fixture
def mock_client() -> MagicMock:
    """기본 mock httpx.Client."""
    client = MagicMock(spec=httpx.Client)
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = _mock_json_response([
        {
            "roadAddr": "서울특별시 강남구 테헤란로 123",
            "roadAddrPart1": "서울특별시 강남구 테헤란로 123",
            "bdMgtNo": "1168010100123450001",
            "detBdNmList": "101동 1503호",
        }
    ])
    resp.raise_for_status.return_value = None
    client.get.return_value = resp
    return client


@pytest.fixture
def channel(mock_client: MagicMock) -> JusoChannel:
    """JusoChannel with mock client."""
    return JusoChannel(api_key="test-key", client=mock_client)


class TestJusoChannel:
    """JusoChannel collect() 기본 동작."""

    def test_channel_attrs(self) -> None:
        """Given JusoChannel class Then channel_name/reliability 설정됨"""
        assert JusoChannel.channel_name == "juso"
        assert JusoChannel.reliability == 0.85

    def test_collect_returns_list(self, channel: JusoChannel,
                                  mock_client: MagicMock) -> None:
        """Given 정상 keyword When collect Then 결과 리스트 반환"""
        result = channel.collect({"keyword": "테헤란로 123"})
        assert len(result) == 1
        assert result[0]["roadAddr"] == "서울특별시 강남구 테헤란로 123"

    def test_collect_passes_correct_params(self, channel: JusoChannel,
                                           mock_client: MagicMock) -> None:
        """Given keyword When collect Then 올바른 params 전달"""
        channel.collect({"keyword": "강남대로"})
        called_params = mock_client.get.call_args[1]["params"]
        assert called_params["keyword"] == "강남대로"
        assert called_params["searchType"] == "floorho"
        assert called_params["confmKey"] == "test-key"

    def test_empty_keyword_returns_empty(self, channel: JusoChannel,
                                         mock_client: MagicMock) -> None:
        """Given 빈 keyword When collect Then 검증 가능"""
        mock_client.get.return_value.json.return_value = _mock_json_response([])
        result = channel.collect({"keyword": ""})
        assert result == []

    def test_empty_response(self, channel: JusoChannel,
                            mock_client: MagicMock) -> None:
        """Given 빈 응답 When collect Then 빈 리스트"""
        mock_client.get.return_value.json.return_value = _mock_json_response([])
        result = channel.collect({"keyword": "없는주소"})
        assert result == []

    def test_http_error_fallback(self, channel: JusoChannel,
                                 mock_client: MagicMock) -> None:
        """Given HTTP 500 When collect Then 빈 리스트 (재시도 후 폴백)"""
        err_resp = MagicMock(spec=httpx.Response, status_code=500)
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=err_resp
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({"keyword": "test"})
        assert result == []

    def test_timeout_fallback(self, channel: JusoChannel,
                              mock_client: MagicMock) -> None:
        """Given 타임아웃 When collect Then 빈 리스트"""
        mock_client.get.side_effect = httpx.TimeoutException(
            "timeout", request=MagicMock()
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda _: None)
            result = channel.collect({"keyword": "test"})
        assert result == []

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Given PUBLIC_DATA_API_KEY 환경변수 When 채널 생성 Then 키 사용"""
        monkeypatch.setenv("PUBLIC_DATA_API_KEY", "env-key-123")
        mock_client = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.json.return_value = _mock_json_response([])
        mock_client.get.return_value = resp

        ch = JusoChannel(client=mock_client)
        ch.collect({"keyword": "test"})
        called = mock_client.get.call_args[1]["params"]
        assert called["confmKey"] == "env-key-123"

    def test_pagination_params(self, channel: JusoChannel,
                               mock_client: MagicMock) -> None:
        """Given current_page/count_per_page When collect Then 전달 확인"""
        channel.collect({"keyword": "test", "current_page": 3, "count_per_page": 50})
        called = mock_client.get.call_args[1]["params"]
        assert called["currentPage"] == 3
        assert called["countPerPage"] == 50
