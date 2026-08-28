"""
NHPLUG OAuth2 인증 — 접근 토큰 발급/캐싱/재시도.

NH투자증권 나무 API 인증 방식:
- Endpoint: POST {domain}/oauth2/token
- Content-Type: application/x-www-form-urlencoded (form-data)
- Parameters: appkey, appsecretkey, grant_type=client_credentials, scope=oob
- 토큰 유효기간: 24시간 (86400초)
- 호출 시 헤더: Authorization: Bearer {token}, x-client-id, x-client-secret
"""
import random
import time

import certifi
import requests

from broker.base import AuthError

# 토큰 발급은 항상 운영 도메인에서만 성공합니다.
# 모의투자 서버(moapi.nhplug.com)는 토큰 발급을 지원하지 않아 403을 반환하므로,
# 전달받은 domain이 모의투자 도메인이면 운영 도메인으로 교체합니다.
LIVE_DOMAIN = "https://api.nhplug.com:8443"

# 발급받은 토큰을 캐시하는 전역 변수
# 프로그램 실행 중 한 번 발급한 토큰을 재사용하여 불필요한 API 호출을 줄입니다
_cached_token = None
_token_expires_at = 0.0


def get_access_token(
    domain: str,
    app_key: str,
    app_secret: str,
    timeout: tuple[float, float] = (10, 30),
    session=None,
) -> str:
    """
    NH투자증권 나무 API에서 access token을 발급받습니다.

    OAuth2 client_credentials 방식:
    - POST {domain}/oauth2/token
    - form-data: appkey, appsecretkey, grant_type=client_credentials, scope=oob

    토큰 캐싱:
    - 한 번 발급받은 토큰은 전역 변수에 저장되어 재사용됩니다.
    - 만료 60초 전에 자동 재발급합니다.

    자동 재시도:
    - 타임아웃(ConnectTimeout, ReadTimeout): 지수 백오프 + jitter 후 재시도 (최대 3회)

    Returns:
        str: access token 문자열

    Raises:
        AuthError: 인증 실패 (잘못된 키, 허용되지 않은 IP 등)
    """
    global _cached_token, _token_expires_at

    now = time.time()

    # 캐시된 토큰이 유효하면 즉시 반환 (만료 60초 전까지)
    if _cached_token is not None and now < _token_expires_at - 60:
        return _cached_token

    # 환경변수가 설정되어 있는지 확인
    if not app_key or not app_secret:
        raise AuthError(
            "환경변수 NHPLUG_APP_KEY와 NHPLUG_APP_SECRET이 설정되어야 합니다. "
            ".env 파일을 확인해주세요."
        )

    # 모의투자 서버(moapi)는 토큰 발급을 지원하지 않으므로(403),
    # 전달받은 domain이 모의투자 도메인이면 운영 도메인으로 교체합니다.
    if "moapi" in domain:
        domain = LIVE_DOMAIN

    url = f"{domain}/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "appkey": app_key,
        "appsecretkey": app_secret,
        "grant_type": "client_credentials",
        "scope": "oob",
    }

    MAX_RETRIES = 3
    network_retry_count = 0

    while True:
        try:
            http = session.post if session else requests.post
            response = http(
                url,
                verify=certifi.where(),
                headers=headers,
                data=data,
                timeout=timeout,
            )

            # HTTP 401/403 — 클라이언트 인증 실패
            if response.status_code in (401, 403):
                raise AuthError(
                    f"NHPLUG 클라이언트 인증 실패 ({response.status_code}): "
                    "appkey 또는 appsecretkey가 잘못되었거나 허용되지 않은 IP입니다."
                )

            response.raise_for_status()
            body = response.json()

            token = body.get("access_token")
            if not token:
                error = body.get("error", "unknown")
                desc = body.get("error_description", "알 수 없는 오류")
                raise AuthError(f"토큰 발급 실패 [{error}]: {desc}")

            expires_in = int(body.get("expires_in", 86400))
            _cached_token = token
            _token_expires_at = now + expires_in
            print("[NHPLUG 인증] 토큰 발급 성공")
            return token

        except AuthError:
            raise

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            network_retry_count += 1
            if network_retry_count <= MAX_RETRIES:
                wait = min(30, 2 ** network_retry_count) * random.uniform(0.75, 1.25)
                print(f"⏳ NHPLUG 토큰 발급 타임아웃: {str(e)[:60]}...")
                print(f"   {wait:.1f}초 후 재시도... ({network_retry_count}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise AuthError(f"NHPLUG 토큰 발급 실패 (네트워크): {str(e)}")