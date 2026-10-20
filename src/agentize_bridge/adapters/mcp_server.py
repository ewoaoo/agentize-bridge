import argparse
import asyncio
import inspect
import json
import os
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool

from ..utils import schema_type
from .http_client import HttpClient


def _create_tool(client: HttpClient, command: dict[str, Any], timeout: float) -> Tool:
    name = command["name"]
    schema = command.get(
        "input_schema",
        {"type": "object", "properties": {}}
    )
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    parameters = []
    annotations = {}

    for key, prop_schema in properties.items():
        annotation = schema_type(prop_schema)
        default = (
            inspect.Parameter.empty
            if key in required
            else prop_schema.get("default", None)
        )

        parameters.append(
            inspect.Parameter(
                key,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=annotation,
            )
        )
        annotations[key] = annotation

    async def invoke(**arguments: Any) -> str:
        result = await asyncio.to_thread(client.call_command, name, arguments, timeout)
        return json.dumps(result, ensure_ascii=False)

    invoke.__name__ = name
    invoke.__doc__ = command.get("description", "")
    invoke.__annotations__ = {**annotations, "return": str}
    invoke.__signature__ = inspect.Signature(parameters)

    tool = Tool.from_function(
        invoke,
        name=name,
        description=command.get("description", ""),
        structured_output=False,
    )
    tool.parameters = schema

    return tool


async def _create_server(base_url: str, *, timeout: float = 30):
    client = HttpClient(base_url, timeout=timeout)
    commands = await asyncio.to_thread(client.get, "/commands")

    tools = [
        _create_tool(client, command, timeout)
        for command in commands
    ]

    return MCPServer(name="agentize-bridge-mcp", tools=tools)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentize-bridge-mcp")
    parser.add_argument(
        "--url",
        default=os.environ.get("AGENTIZE_BRIDGE_URL", "http://127.0.0.1:8765"),
        help="正在运行的 Agentize Bridge 服务器的基础 URL",
    )
    parser.add_argument("--timeout", type=float, default=30, help="command timeout in seconds")
    options = parser.parse_args()
    server = asyncio.run(_create_server(options.url, timeout=options.timeout))
    server.run("stdio")


if __name__ == "__main__":
    main()
