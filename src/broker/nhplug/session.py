"""
NHPLUG HTTP 세션 관리 — NH투자증권 나무 API 공통 헤더/인증 설정.

NHPLUG API는 OAuth2 Bearer 토큰 + x-client-id/x-client-secret 헤더를 사용합니다.
모든 요청에 공통 헤더를 자동으로 추가하고 certifi 인증서로 TLS 검증을 수행합니다.
"""
import certifi
import requests


class NHPlugSession:
    """
    NH투자증권 나무 API 호출을 위한 requests.Session 래퍼.

    모든 요청에 다음 헤더를 자동으로 추가합니다:
    - Authorization: Bearer {access_token}
    - x-client-id: {appkey}
    - x-client-secret: {appsecret}
    - Content-Type: application/json; charset=utf-8
    """

    def __init__(
        self,
        domain: str,
        app_key: str,
        app_secret: str,
        timeout: tuple[float, float] = (10, 30),
    ):
        """
        Parameters:
            domain: NHPLUG API 베이스 URL
                    (실전: https://api.nhplug.com:8443, 모의: https://moapi.nhplug.com:8443)
            app_key: NHPLUG_APP_KEY (x-client-id 헤더 값)
            app_secret: NHPLUG_APP_SECRET (x-client-secret 헤더 값)
            timeout: (connect_timeout, read_timeout) 초 단위
        """
        self._domain = domain
        self._app_key = app_key
        self._app_secret = app_secret
        self._timeout = timeout

        self._session = requests.Session()
        self._session.verify = certifi.where()

    @property
    def timeout(self) -> tuple[float, float]:
        return self._timeout

    def _build_headers(
        self,
        token: str,
        extra_headers: dict | None = None,
    ) -> dict:
        """공통 헤더를 구성합니다."""
        headers = {
            "Authorization": f"Bearer {token}",
            "x-client-id": self._app_key,
            "x-client-secret": self._app_secret,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def request(
        self,
        method: str,
        path: str,
        token: str,
        json_body: dict | None = None,
        extra_headers: dict | None = None,
        domain: str | None = None,
    ) -> requests.Response:
        """
        API 요청을 실행합니다.

        Parameters:
            method: HTTP 메서드 (NHPLUG는 대부분 POST)
            path: API 경로 (예: "/gbstock/quote/v1/current")
            token: OAuth2 access token
            json_body: JSON 요청 바디
            extra_headers: 추가 헤더
            domain: 요청에 사용할 베이스 도메인 (기본값: 모드별 도메인 self._domain).
                    시세 API는 모의투자 서버(moapi)가 지원하지 않으므로
                    운영 도메인(api.nhplug.com)으로 라우팅할 때 사용합니다.

        Returns:
            requests.Response
        """
        base = domain or self._domain
        url = f"{base}{path}"
        headers = self._build_headers(token, extra_headers)
        return self._session.request(
            method, url, headers=headers, json=json_body, timeout=self._timeout
        )

    def post(self, url: str, **kwargs) -> requests.Response:
        """
        토큰 발급 등 외부 URL용 POST 래퍼.

        auth.py에서 form-data 토큰 발급 시 사용합니다.
        """
        kwargs.setdefault("timeout", self._timeout)
        return self._session.post(url, **kwargs)

    def close(self):
        """HTTP 세션을 종료합니다."""
        self._session.close()