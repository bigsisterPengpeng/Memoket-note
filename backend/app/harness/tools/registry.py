"""Register, describe and dispatch tools without depending on a harness runtime."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolContext:
    """Per-call document, identity and scratch context supplied by the caller."""

    user: str
    note_id: str = ""
    note_title: str = ""


    content: str = ""
    cursor: int = 0
    scope: str = "all"


    intent: str = ""


    intent_checked: tuple[str, ...] = ()


    tray: list[dict] = field(default_factory=list)

    # Scratch space the caller owns; the tool pool never interprets it.
    # This exists so tools can share mutable state with whatever is driving
    # them **without the tool layer knowing what that driver is**. The harness
    # puts its own list object in here, so a tool appending to it writes
    # straight through to the run's state -- and ``registry`` still has no
    # idea a harness exists. Any other caller can put whatever it likes here.
    scratch: dict = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, dict]
    required: list[str]
    handler: Callable[..., Any]
    group: str = "memory"


    max_calls_per_round: int = 3

    def spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.params,
                    "required": self.required,
                },
            },
        }


_REGISTRY: dict[str, Tool] = {}


def register(*, name: str, description: str, params: dict[str, dict],
             required: list[str] | None = None, group: str = "memory",
             max_calls_per_round: int = 3) -> Callable:
    def deco(fn: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"Duplicate tool registration: {name}")
        _REGISTRY[name] = Tool(
            name=name, description=description, params=params,
            required=list(required or []), handler=fn, group=group,
            max_calls_per_round=max_calls_per_round,
        )
        return fn
    return deco


def get(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def names(groups: list[str] | None = None) -> list[str]:
    if groups is None:
        return sorted(_REGISTRY)
    allowed = set(groups)
    return sorted(n for n, t in _REGISTRY.items() if t.group in allowed)


def specs(groups: list[str] | None = None) -> list[dict]:
    """Render the registered tools as model tool specifications."""
    return [_REGISTRY[n].spec() for n in names(groups)]


class ToolError(Exception):
    """A recoverable tool failure returned to the model as text."""


def _await(coro, name: str) -> str:
    """Run an asynchronous handler without nesting the current event loop."""
    import asyncio
    import concurrent.futures as _f

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        result = asyncio.run(coro)
    else:
        with _f.ThreadPoolExecutor(max_workers=1) as ex:
            result = ex.submit(asyncio.run, coro).result()
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


def dispatch(name: str, arguments: str | dict, ctx: ToolContext) -> str:
    """Validate and execute one tool call, returning recoverable failures as text."""
    tool = _REGISTRY.get(name)
    if tool is None:
        return f"(Unknown tool {name}. Available tools: {', '.join(names())})"

    if isinstance(arguments, str):
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return f"(Arguments for {name} are not valid JSON: {arguments[:200]})"
    else:
        args = dict(arguments or {})

    if not isinstance(args, dict):
        return f"(Arguments for {name} must be an object; received {type(args).__name__})"

    missing = [k for k in tool.required if k not in args or args[k] in ("", None)]
    if missing:
        return f"(Missing required arguments for {name}: {', '.join(missing)})"


    sig = inspect.signature(tool.handler)
    accepted = {k: v for k, v in args.items() if k in sig.parameters}
    try:
        result = tool.handler(ctx, **accepted)
        if inspect.isawaitable(result):


            return _await(result, name)
    except ToolError as exc:
        return f"Execution failed ({name}): {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Execution error ({name}): {type(exc).__name__}: {exc}"
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


def is_tool_notice(result: str) -> bool:
    """Recognize status/error text in current and legacy tool responses."""
    return result.lstrip().startswith(("(", "\uff08", "Execution failed", "Execution error"))


def describe(groups: list[str] | None = None) -> str:
    """Describe the selected tools for the system prompt."""
    lines = []
    for n in names(groups):
        t = _REGISTRY[n]
        lines.append(f"- {t.name}: {t.description}")
    return "\n".join(lines)


def _reset_for_tests() -> None:
    _REGISTRY.clear()


def _snapshot() -> dict[str, Tool]:
    return dict(_REGISTRY)


def _restore(snapshot: dict[str, Tool]) -> None:
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)
