import json
import os
import sys
from argparse import ArgumentParser

from .http_client import HttpClient, HttpClientError


def run_cli(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(prog="agentize-bridge")
    parser.add_argument("--url", default=os.getenv("AGENTIZE_BRIDGE_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--timeout", type=float, default=30)

    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("list")

    call_parser = subparsers.add_parser("call")
    call_parser.add_argument("command")
    call_parser.add_argument("--args", default="{}")

    options = parser.parse_args(argv)
    client = HttpClient(options.url, timeout=options.timeout)

    try:
        if options.action == "list":
            result = client.get("/commands")
        else:
            arguments = json.loads(options.args)
            if not isinstance(arguments, dict):
                raise ValueError("--args 必须是一个 JSON 对象")
            result = client.call_command(options.command, arguments, timeout=options.timeout)

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (HttpClientError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误:{exc}", file=sys.stderr)
        return 1


def main():
    return run_cli()
