import argparse
import asyncio
import json
import os
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from .. import __version__
from .http_client import HttpClient, HttpClientError


def _create_server(client: HttpClient, commands: list[dict[str, Any]], timeout: float) -> Server:
    """用 /commands 返回的元数据构建 MCP Server。

    input_schema 原样透传；参数校验只由 HTTP 服务端负责。
    """
    tools = {
        command["name"]: Tool(
            name=command["name"],
            description=command.get("description", ""),
            input_schema=command.get("input_schema", {"type": "object", "properties": {}}),
        )
        for command in commands
    }

    async def list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListToolsResult:
        return ListToolsResult(tools=list(tools.values()))

    async def call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
        if params.name not in tools:
            raise ValueError(f"未知的工具: {params.name}")
        try:
            result = await asyncio.to_thread(client.call_command, params.name, params.arguments or {}, timeout)
        except HttpClientError as exc:
            # 低层 Server 会把 handler 里抛出的异常变成通用的协议错误，模型读不到原因；
            # 这里改为返回 is_error 结果，让模型看到服务端的校验信息并自行重试。
            return CallToolResult(content=[TextContent(type="text", text=str(exc))], is_error=True)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))])

    return Server("agentize-bridge-mcp", version=__version__, on_list_tools=list_tools, on_call_tool=call_tool)


async def _serve(base_url: str, *, timeout: float = 30) -> None:
    client = HttpClient(base_url, timeout=timeout)
    commands = await asyncio.to_thread(client.get, "/commands")
    server = _create_server(client, commands, timeout)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentize-bridge-mcp")
    parser.add_argument(
        "--url",
        default=os.environ.get("AGENTIZE_BRIDGE_URL", "http://127.0.0.1:8765"),
        help="正在运行的 Agentize Bridge 服务器的基础 URL",
    )
    parser.add_argument("--timeout", type=float, default=30, help="command timeout in seconds")
    options = parser.parse_args()
    asyncio.run(_serve(options.url, timeout=options.timeout))


if __name__ == "__main__":
    main()
