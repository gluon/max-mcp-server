"""Operation history for undo/redo support in maxmsp-mcp.

Each mutation (create, delete, connect, disconnect, attribute change, rename)
is recorded as an Entry. The History stack supports undo and redo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


@dataclass
class Entry:
    """A recorded mutation that can be undone."""

    kind: str  # create | delete | connect | disconnect | setattr | rename | clear
    description: str
    # For create: {name, maxclass, text, x, y}
    # For delete: {name, maxclass, text, x, y}  (inverse of create)
    # For connect: {from_name, outlet, to_name, inlet}
    # For disconnect: {from_name, outlet, to_name, inlet}
    # For setattr: {name, attr, old_value, new_value}
    # For rename: {old_name, new_name}
    # For clear: {objects: [...], connections: [...]}
    forward: dict = field(default_factory=dict)
    inverse: dict = field(default_factory=dict)


class History:
    """Stack of operations with undo/redo support."""

    def __init__(self, max_depth: int = 200):
        self._past: List[Entry] = []
        self._future: List[Entry] = []
        self._max_depth = max_depth
        self._batch: Optional[list] = None  # batch entries (transaction)

    def push(self, entry: Entry) -> None:
        """Record a completed operation."""
        if self._batch is not None:
            self._batch.append(entry)
        else:
            self._past.append(entry)
            if len(self._past) > self._max_depth:
                self._past.pop(0)
            self._future.clear()  # new branch invalidates redo

    def begin_batch(self) -> None:
        """Start a batch (group operations as one undoable unit)."""
        self._batch = []

    def commit_batch(self) -> None:
        """End batch. All entries since begin_batch become one undoable unit."""
        if self._batch is not None:
            if self._batch:
                # Wrap the batch as a single composite entry
                desc = "; ".join(e.description for e in self._batch)
                composite = Entry(
                    kind="batch",
                    description=f"batch: {desc}",
                    forward={"batch": self._batch},
                    inverse={"batch": list(reversed(self._batch))},
                )
                self._past.append(composite)
                if len(self._past) > self._max_depth:
                    self._past.pop(0)
                self._future.clear()
            self._batch = None

    def cancel_batch(self) -> None:
        """Cancel batch without committing."""
        self._batch = None

    @property
    def can_undo(self) -> bool:
        return len(self._past) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._future) > 0

    def undo_label(self) -> Optional[str]:
        if self._past:
            return self._past[-1].description
        return None

    def redo_label(self) -> Optional[str]:
        if self._future:
            return self._future[-1].description
        return None

    def pop_undo(self) -> Optional[Entry]:
        """Pop the top entry for undoing (moves to future)."""
        if not self._past:
            return None
        entry = self._past.pop()
        self._future.append(entry)
        return entry

    def pop_redo(self) -> Optional[Entry]:
        """Pop the top entry for redoing (moves to past)."""
        if not self._future:
            return None
        entry = self._future.pop()
        self._past.append(entry)
        return entry

    def summary(self) -> str:
        parts = []
        if self._past:
            parts.append(f"past: {len(self._past)} ops")
        if self._future:
            parts.append(f"future: {len(self._future)} ops (redo available)")
        if self._batch is not None:
            parts.append(f"batch in progress: {len(self._batch)} ops")
        return "undo history: " + (", ".join(parts) if parts else "empty")
