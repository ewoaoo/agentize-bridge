import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote


class HttpClientError(Exception):
    pass


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict | None = None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method=method
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
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

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body: dict | None = None):
        return self.request("POST", path, body)

    def call_command(self, name: str, arguments: dict, timeout: float | None = None):
        path = f"/command/{quote(name, safe='')}"
        if timeout is not None:
            path += f"?timeout={timeout}"
        return self.post(path, arguments)
