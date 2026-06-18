from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from .errors import InvalidSnapshot, InvalidValue, StackOverflow, StackUnderflow
from .values import Value, ensure_value, is_value


@dataclass(frozen=True, slots=True)
class StackSnapshot:
    items: tuple[Value, ...]
    max_depth: int | None = None

    def __post_init__(self) -> None:
        if self.max_depth is not None and self.max_depth < 0:
            raise InvalidSnapshot(
                "Snapshot max_depth cannot be negative",
                context={"max_depth": self.max_depth},
            )
        if self.max_depth is not None and len(self.items) > self.max_depth:
            raise InvalidSnapshot(
                "Snapshot depth exceeds max_depth",
                context={
                    "depth": len(self.items),
                    "max_depth": self.max_depth,
                },
            )
        for item in self.items:
            if not is_value(item):
                raise InvalidSnapshot(
                    "Snapshot contains an invalid item",
                    context={"received": type(item).__name__},
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "max_depth": self.max_depth,
        }


class Stack:
    __slots__ = ("_items", "_max_depth")

    def __init__(
        self,
        items: Iterable[Value] | None = None,
        *,
        max_depth: int | None = None,
    ) -> None:
        if max_depth is not None and max_depth < 0:
            raise InvalidValue(
                "max_depth cannot be negative",
                context={"field": "max_depth", "received": max_depth},
            )
        self._max_depth = max_depth
        self._items: list[Value] = []
        if items is not None:
            for item in items:
                self.push(item)

    def push(self, value: object) -> None:
        item = ensure_value(value)
        if self._max_depth is not None and len(self._items) >= self._max_depth:
            raise StackOverflow(
                context={
                    "max_depth": self._max_depth,
                    "current_depth": len(self._items),
                }
            )
        self._items.append(item)

    def pop(self) -> Value:
        if not self._items:
            raise StackUnderflow(context={"operation": "pop"})
        return self._items.pop()

    def peek(self) -> Value:
        if not self._items:
            raise StackUnderflow(context={"operation": "peek"})
        return self._items[-1]

    def depth(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items.clear()

    def snapshot(self) -> StackSnapshot:
        return StackSnapshot(items=tuple(self._items), max_depth=self._max_depth)

    def restore(self, snapshot: object) -> None:
        if not isinstance(snapshot, StackSnapshot):
            raise InvalidSnapshot(
                "restore expects a StackSnapshot",
                context={"received": type(snapshot).__name__},
            )
        self._items = list(snapshot.items)
        self._max_depth = snapshot.max_depth

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Value]:
        return iter(tuple(self._items))

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Stack)
            and self._max_depth == other._max_depth
            and tuple(self._items) == tuple(other._items)
        )

    def __repr__(self) -> str:
        return f"Stack(items={tuple(self._items)!r}, max_depth={self._max_depth!r})"


__all__ = ["Stack", "StackSnapshot"]
