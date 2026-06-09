"""Server-side mirror of what we created in Max.

We assign stable scripting *names* (obj_0, obj_1, ...). Max addresses objects
by these names via [thispatcher], so the mapping never drifts on manual edits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MaxObject:
    name: str
    maxclass: str
    text: str
    x: int
    y: int


@dataclass
class PatchState:
    initialized: bool = False
    _counter: int = 0
    objects: Dict[str, MaxObject] = field(default_factory=dict)

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
