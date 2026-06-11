"""Server-side mirror of Max patch state with subpatcher context and undo hooks.

Tracks every object the server created, the current patcher context,
and provides undo/redo integration via operations.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .operations import Entry, History


@dataclass
class MaxObject:
    name: str
    maxclass: str
    text: str
    x: int
    y: int
    patcher: str = ""  # "" = top-level, otherwise subpatcher name


@dataclass
class PatchState:
    initialized: bool = False
    dsp_on: bool = False
    _counter: int = 0
    objects: Dict[str, MaxObject] = field(default_factory=dict)
    _patcher_stack: List[str] = field(default_factory=list)  # current subpatcher path
    history: History = field(default_factory=History)

    @property
    def current_patcher(self) -> str:
        """Empty string = top-level, otherwise patcher name for subpatchers."""
        return self._patcher_stack[-1] if self._patcher_stack else ""

    @property
    def patcher_depth(self) -> int:
        return len(self._patcher_stack)

    def push_patcher(self, name: str) -> None:
        self._patcher_stack.append(name)

    def pop_patcher(self) -> Optional[str]:
        if self._patcher_stack:
            return self._patcher_stack.pop()
        return None

    def next_name(self, prefix: str = "obj") -> str:
        name = f"{prefix}_{self._counter}"
        self._counter += 1
        return name

    def register(self, obj: MaxObject) -> None:
        self.objects[obj.name] = obj

    def forget(self, name: str) -> bool:
        return self.objects.pop(name, None) is not None

    def names(self) -> List[str]:
        return list(self.objects.keys())

    def reset(self) -> None:
        self.objects.clear()
        self._counter = 0
        self._patcher_stack.clear()

    def find_by_class(self, maxclass: str) -> List[MaxObject]:
        return [o for o in self.objects.values() if o.maxclass == maxclass]

    def find_by_text(self, substring: str) -> List[MaxObject]:
        return [o for o in self.objects.values() if substring in o.text]

    def summary(self) -> str:
        lines = [f"{len(self.objects)} objects in state"]
        if self.current_patcher:
            lines.append(f"  current patcher: {self.current_patcher}")
        lines.append(self.history.summary())
        return "\n".join(lines)
