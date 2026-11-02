import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote

_MARGIN_SECONDS = 5.0


class HttpClientError(Exception):
    pass


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 30, margin: float = _MARGIN_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.margin = margin

    def request(self, method: str, path: str, body: dict | None = None, timeout: float | None = None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method
        )

        socket_timeout = self.timeout if timeout is None else timeout

        try:
            with urlopen(request, timeout=socket_timeout) as response:
                content = response.read()
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise HttpClientError(f"HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise HttpClientError(f"HTTP 请求失败: {exc.reason}") from exc
        except (TimeoutError, ValueError) as exc:
            raise HttpClientError(f"HTTP 请求失败: {exc}") from exc

        if not content:
            return None

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise HttpClientError("无效的 JSON 响应") from exc

    def get(self, path: str, timeout: float | None = None):
        return self.request("GET", path, timeout=timeout)

    def post(self, path: str, body: dict | None = None, timeout: float | None = None):
        return self.request("POST", path, body, timeout=timeout)

    def call_command(self, name: str, arguments: dict, timeout: float):
        path = f"/command/{quote(name, safe='')}?timeout={timeout}"
        return self.post(path, arguments, timeout=timeout + self.margin)
