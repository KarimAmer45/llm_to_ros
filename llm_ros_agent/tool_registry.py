from typing import Any, Callable, Dict, Awaitable

ToolFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolFn] = {}

    def register(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def get(self, name: str) -> ToolFn:
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools
