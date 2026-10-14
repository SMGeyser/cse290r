"""Simple command-line client for Qwen through OpenRouter.

Usage:
    $env:OPENROUTER_API_KEY = "your-key"
    python qwen_client.py "Explain recursion in one paragraph."

If no prompt argument is supplied, the prompt is read from standard input.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3.8-27b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with Qwen through OpenRouter.")
    parser.add_argument("prompt", nargs="?", help="User message; reads stdin when omitted.")
    parser.add_argument("--system", help="Optional system message.")
    parser.add_argument("--max-tokens", type=int, help="Maximum number of output tokens.")
    parser.add_argument("--temperature", type=float, help="Sampling temperature.")
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Wait for the complete response instead of printing tokens as they arrive.",
    )
    return parser.parse_args()


def get_prompt(argument: str | None) -> str:
    prompt = argument if argument is not None else sys.stdin.read()
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Provide a prompt argument or pipe prompt text through stdin.")
    return prompt


def build_payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "stream": not args.no_stream,
    }
    if args.max_tokens is not None:
        payload["max_tokens"] = args.max_tokens
    if args.temperature is not None:
        payload["temperature"] = args.temperature
    return payload


def print_error(error: Exception) -> None:
    if isinstance(error, HTTPError):
        body = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            message = body
        print(f"OpenRouter returned HTTP {error.code}: {message}", file=sys.stderr)
    elif isinstance(error, URLError):
        print(f"Could not reach OpenRouter: {error.reason}", file=sys.stderr)
    else:
        print(str(error), file=sys.stderr)


def print_non_streaming(response) -> None:
    data = json.loads(response.read().decode("utf-8"))
    try:
        print(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"Unexpected OpenRouter response: {data}") from error


def print_streaming(response) -> None:
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        choices = chunk.get("choices", [])
        if not choices:
            continue
        text = choices[0].get("delta", {}).get("content")
        if text:
            print(text, end="", flush=True)
    print()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY before running this program.", file=sys.stderr)
        return 1

    try:
        prompt = get_prompt(args.prompt)
        request = Request(
            API_URL,
            data=json.dumps(build_payload(args, prompt)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "Local Qwen CLI",
            },
            method="POST",
        )
        with urlopen(request, timeout=120) as response:
            if args.no_stream:
                print_non_streaming(response)
            else:
                print_streaming(response)
    except (HTTPError, URLError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print_error(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
