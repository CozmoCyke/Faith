from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .capabilities import CapabilitySet
from .contracts import StackContract, ValueKind
from .dictionary import UserWord
from .errors import InvalidValue


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted((data or {}).items())))


def contract_from_dict(data: Mapping[str, Any] | None) -> StackContract | None:
    if data is None:
        return None
    if not isinstance(data, Mapping):
        raise InvalidValue(
            "Contract payload must be a mapping",
            context={"received": type(data).__name__},
        )
    inputs = tuple(ValueKind.parse(str(item)) for item in data.get("inputs", ()))
    outputs = tuple(ValueKind.parse(str(item)) for item in data.get("outputs", ()))
    return StackContract(inputs, outputs)


def contract_to_dict(contract: StackContract | None) -> dict[str, Any] | None:
    if contract is None:
        return None
    return contract.to_dict()


def capability_set_from_dict(data: Mapping[str, Any] | None) -> CapabilitySet:
    if data is None:
        return CapabilitySet.none()
    granted = data.get("granted", ())
    if not isinstance(granted, list | tuple):
        raise InvalidValue(
            "Capability payload must contain a granted list",
            context={"received": type(granted).__name__},
        )
    return CapabilitySet.of(*tuple(str(item) for item in granted))


@dataclass(frozen=True, slots=True)
class WordVersion:
    name: str
    version: int
    body: tuple[str, ...]
    dependencies: tuple[str, ...]
    dependency_versions: tuple[tuple[str, int], ...]
    primitive_dependencies: tuple[str, ...]
    required_capabilities: CapabilitySet
    contract: StackContract | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})
    created_sequence: int = 0
    content_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if self.version < 1:
            raise InvalidValue(
                "Word version must be positive",
                context={"version": self.version},
            )

    def dependency_version_map(self) -> dict[str, int]:
        return {name: version for name, version in self.dependency_versions}

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "body": list(self.body),
            "contract": contract_to_dict(self.contract),
            "dependencies": list(self.dependencies),
            "dependency_versions": [
                {"name": name, "version": version}
                for name, version in self.dependency_versions
            ],
            "primitive_dependencies": list(self.primitive_dependencies),
            "required_capabilities": self.required_capabilities.to_dict(),
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.canonical_payload())

    def compute_hash(self) -> str:
        digest = hashlib.sha256(self.canonical_json().encode("utf-8"))
        return digest.hexdigest()

    def with_hash(self) -> WordVersion:
        return WordVersion(
            name=self.name,
            version=self.version,
            body=self.body,
            dependencies=self.dependencies,
            dependency_versions=self.dependency_versions,
            primitive_dependencies=self.primitive_dependencies,
            required_capabilities=self.required_capabilities,
            contract=self.contract,
            metadata=self.metadata,
            created_sequence=self.created_sequence,
            content_hash=self.compute_hash(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "body": list(self.body),
            "contract": contract_to_dict(self.contract),
            "dependencies": list(self.dependencies),
            "dependency_versions": [
                {"name": name, "version": version}
                for name, version in self.dependency_versions
            ],
            "primitive_dependencies": list(self.primitive_dependencies),
            "required_capabilities": self.required_capabilities.to_dict(),
            "metadata": dict(self.metadata),
            "created_sequence": self.created_sequence,
            "content_hash": self.content_hash or self.compute_hash(),
        }

    @classmethod
    def from_user_word(
        cls,
        word: UserWord,
        *,
        version: int,
        dependency_versions: Mapping[str, int],
        created_sequence: int,
    ) -> WordVersion:
        pairs = tuple(
            sorted(
                (name, int(number))
                for name, number in dependency_versions.items()
            )
        )
        return cls(
            name=word.name,
            version=version,
            body=word.body,
            dependencies=word.dependencies,
            dependency_versions=pairs,
            primitive_dependencies=word.primitive_dependencies,
            required_capabilities=word.required_capabilities,
            contract=word.contract,
            metadata=word.metadata,
            created_sequence=created_sequence,
        ).with_hash()

    def to_user_word(self) -> UserWord:
        return UserWord(
            name=self.name,
            body=self.body,
            dependencies=self.dependencies,
            primitive_dependencies=self.primitive_dependencies,
            required_capabilities=self.required_capabilities,
            contract=self.contract,
            metadata=self.metadata,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WordVersion:
        if not isinstance(data, Mapping):
            raise InvalidValue(
                "WordVersion payload must be a mapping",
                context={"received": type(data).__name__},
            )
        dependency_versions = tuple(
            (
                str(item["name"]),
                int(item["version"]),
            )
            for item in data.get("dependency_versions", ())
        )
        return cls(
            name=str(data["name"]),
            version=int(data["version"]),
            body=tuple(str(item) for item in data.get("body", ())),
            contract=contract_from_dict(data.get("contract")),
            dependencies=tuple(str(item) for item in data.get("dependencies", ())),
            dependency_versions=dependency_versions,
            primitive_dependencies=tuple(
                str(item) for item in data.get("primitive_dependencies", ())
            ),
            required_capabilities=capability_set_from_dict(
                data.get("required_capabilities")
            ),
            metadata=_freeze_mapping(data.get("metadata")),
            created_sequence=int(data.get("created_sequence", 0)),
            content_hash=str(data.get("content_hash", "")),
        )


__all__ = [
    "WordVersion",
    "canonical_json",
    "contract_from_dict",
    "contract_to_dict",
    "capability_set_from_dict",
]
