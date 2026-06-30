"""Supabase 클라이언트 연결 모듈.

.env 에서 SUPABASE_URL / SUPABASE_SERVICE_KEY(또는 SUPABASE_ANON_KEY) 를 읽어
supabase-py 클라이언트를 생성한다. 실제 DB 연결은 get_client() 호출 시점에
일어나며, 모듈 임포트 자체는 .env 가 없어도 성공해야 한다(검증 명령 준수).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from supabase import Client
from supabase import create_client

# 모듈 임포트 시 .env 로드. 파일이 없어도 예외를 던지지 않는다.
load_dotenv()

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_KEY"
_ANON_KEY_ENV = "SUPABASE_ANON_KEY"


class SupabaseConfigError(ValueError):
    """Supabase 접속에 필요한 환경변수가 누락됐을 때 발생."""


def _read_credentials() -> tuple[str, str]:
    """환경변수에서 (url, key) 를 읽는다.

    service key 를 우선한다(서버사이드 ETL용). 없으면 anon key 로 폴백.
    둘 중 하나라도 없으면 SupabaseConfigError.
    """
    url = os.environ.get(_URL_ENV)
    key = os.environ.get(_SERVICE_KEY_ENV) or os.environ.get(_ANON_KEY_ENV)
    if not url:
        raise SupabaseConfigError(
            f"{_URL_ENV} 환경변수가 없습니다. .env 를 확인하세요."
        )
    if not key:
        raise SupabaseConfigError(
            f"{_SERVICE_KEY_ENV} 또는 {_ANON_KEY_ENV} 환경변수가 없습니다. "
            ".env 를 확인하세요."
        )
    return url, key


def get_client() -> Client:
    """Supabase 클라이언트를 반환한다.

    환경변수가 누락됐으면 SupabaseConfigError(ValueError) 를 발생시킨다.
    클라이언트는 호출마다 새로 생성한다(싱글톤 아님) — ETL 배치처럼
    수명이 명확한 사용처에서 with/lifecycle 을 직접 관리하기 위함.
    """
    url, key = _read_credentials()
    return create_client(url, key)


__all__ = ["SupabaseConfigError", "get_client"]
