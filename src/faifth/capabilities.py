from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .errors import InvalidCapability

_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9._-]*$")


@dataclass(frozen=True, slots=True, order=True)
class Capability:
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise InvalidCapability(
                "Capability name cannot be empty",
                context={"name": self.name},
            )
        if not _CAPABILITY_RE.fullmatch(self.name):
            raise InvalidCapability(
                "Capability name is invalid",
                context={"name": self.name},
            )

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name}


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    granted: frozenset[Capability]

    def __post_init__(self) -> None:
        normalized = frozenset(self._coerce(item) for item in self.granted)
        object.__setattr__(self, "granted", normalized)

    @classmethod
    def of(cls, *names: str | Capability) -> CapabilitySet:
        return cls(frozenset(cls._coerce(name) for name in names))

    @classmethod
    def none(cls) -> CapabilitySet:
        return cls(frozenset())

    @classmethod
    def strict_defaults(cls) -> CapabilitySet:
        return cls.none()

    @classmethod
    def development_defaults(cls) -> CapabilitySet:
        return cls.of(
            "core.compute",
            "core.stack",
            "dictionary.define",
            "dictionary.read",
            "introspection.read",
            "transaction.manage",
        )

    @staticmethod
    def _coerce(item: str | Capability) -> Capability:
        if isinstance(item, Capability):
            return item
        if not isinstance(item, str):
            raise InvalidCapability(
                "Capability must be a string or Capability",
                context={"received": type(item).__name__},
            )
        return Capability(item)

    @staticmethod
    def _coerce_set(value: CapabilitySet | Iterable[str | Capability]) -> CapabilitySet:
        if isinstance(value, CapabilitySet):
            return value
        return CapabilitySet.of(*tuple(value))

    def __iter__(self):
        return iter(tuple(sorted(self.granted)))

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Capability):
            return item in self.granted
        if isinstance(item, str):
            return Capability(item) in self.granted
        return False

    def __bool__(self) -> bool:
        return bool(self.granted)

    def to_tuple(self) -> tuple[str, ...]:
        return tuple(capability.name for capability in self)

    def to_dict(self) -> dict[str, Any]:
        return {"granted": list(self.to_tuple())}

    def issubset(self, other: CapabilitySet | Iterable[str | Capability]) -> bool:
        other_set = self._coerce_set(other)
        return self.granted.issubset(other_set.granted)

    def issuperset(self, other: CapabilitySet | Iterable[str | Capability]) -> bool:
        other_set = self._coerce_set(other)
        return self.granted.issuperset(other_set.granted)

    def allows(self, required: CapabilitySet | Iterable[str | Capability]) -> bool:
        return self.issuperset(required)

    def missing(
        self, required: CapabilitySet | Iterable[str | Capability]
    ) -> CapabilitySet:
        required_set = self._coerce_set(required)
        return CapabilitySet(required_set.granted.difference(self.granted))

    def union(self, other: CapabilitySet | Iterable[str | Capability]) -> CapabilitySet:
        other_set = self._coerce_set(other)
        return CapabilitySet(self.granted.union(other_set.granted))

    def intersection(
        self, other: CapabilitySet | Iterable[str | Capability]
    ) -> CapabilitySet:
        other_set = self._coerce_set(other)
        return CapabilitySet(self.granted.intersection(other_set.granted))

    def difference(
        self, other: CapabilitySet | Iterable[str | Capability]
    ) -> CapabilitySet:
        other_set = self._coerce_set(other)
        return CapabilitySet(self.granted.difference(other_set.granted))


__all__ = ["Capability", "CapabilitySet"]
