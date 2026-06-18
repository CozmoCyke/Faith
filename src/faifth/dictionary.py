from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .contracts import StackContract, ValueKind
from .errors import (
    DuplicateWord,
    InvalidDefinition,
    InvalidValue,
    ProtectedWord,
    RecursiveDefinition,
    StaticContractViolation,
    TypeMismatch,
    UnknownWord,
    UnverifiableContract,
)
from .primitives import DEFAULT_PRIMITIVE_MAP, Primitive
from .tokenizer import Token

_WORD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _is_int_literal(text: str) -> bool:
    if text.startswith("-"):
        return len(text) > 1 and text[1:].isdigit()
    return text.isdigit()


def _is_bool_literal(text: str) -> bool:
    return text in {"true", "false"}


def _is_literal(text: str) -> bool:
    return _is_int_literal(text) or _is_bool_literal(text)


def _coerce_token_text(token: str | Token) -> str:
    return token if isinstance(token, str) else token.text


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(sorted((data or {}).items())))


def _kind_from_literal(text: str) -> ValueKind:
    if _is_int_literal(text):
        return ValueKind.INT
    if _is_bool_literal(text):
        return ValueKind.BOOL
    raise InvalidValue(
        "Unsupported literal for abstract contract analysis",
        context={"literal": text},
    )


@dataclass(frozen=True, slots=True)
class UserWord:
    name: str
    body: tuple[str, ...]
    dependencies: tuple[str, ...]
    primitive_dependencies: tuple[str, ...] = ()
    contract: StackContract | None = None
    source: str | None = None
    definition_index: int | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if not self.name or not _WORD_NAME_RE.fullmatch(self.name):
            raise InvalidValue(
                "UserWord requires a valid name",
                context={"name": self.name},
            )
        if not self.body:
            raise InvalidDefinition(
                "UserWord body cannot be empty",
                context={"name": self.name},
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "user",
            "name": self.name,
            "body": list(self.body),
            "dependencies": list(self.dependencies),
            "primitive_dependencies": list(self.primitive_dependencies),
            "contract": None if self.contract is None else self.contract.to_dict(),
            "source": self.source,
            "definition_index": self.definition_index,
            "metadata": dict(self.metadata),
        }


class Dictionary:
    def __init__(
        self,
        *,
        primitives: Mapping[str, Primitive] | None = None,
    ) -> None:
        self._primitives = (
            MappingProxyType(dict(primitives))
            if primitives is not None
            else DEFAULT_PRIMITIVE_MAP
        )
        self._user_words: dict[str, UserWord] = {}

    @property
    def primitives(self) -> Mapping[str, Primitive]:
        return self._primitives

    def has(self, name: str) -> bool:
        return name in self._primitives or name in self._user_words

    def resolve(self, name: str) -> Primitive | UserWord | None:
        primitive = self._primitives.get(name)
        if primitive is not None:
            return primitive
        return self._user_words.get(name)

    def inspect(self, name: str) -> dict[str, Any]:
        entry = self.resolve(name)
        if entry is None:
            raise UnknownWord(name, index=-1)
        if isinstance(entry, Primitive):
            return entry.to_dict()
        return entry.to_dict()

    def list_words(self) -> tuple[str, ...]:
        return tuple(self._primitives) + tuple(self._user_words)

    def list_user_words(self) -> tuple[str, ...]:
        return tuple(self._user_words)

    def validate_name(self, name: str) -> None:
        if not isinstance(name, str) or not name:
            raise InvalidDefinition(
                "Definition name cannot be empty",
                context={"name": name},
            )
        if name in {":", ";", "(", ")", "--"}:
            raise InvalidDefinition(
                "Definition name is invalid",
                context={"name": name},
            )
        if _is_literal(name):
            raise InvalidDefinition(
                "Definition name cannot be a literal",
                context={"name": name},
            )
        if not _WORD_NAME_RE.fullmatch(name):
            raise InvalidDefinition(
                "Definition name is invalid",
                context={"name": name},
            )
        if name in self._primitives:
            raise ProtectedWord(name, context={"name": name})
        if name in self._user_words:
            raise DuplicateWord(name, context={"name": name})

    def validate_user_word(
        self,
        name: str,
        body: Iterable[str | Token],
        *,
        contract: StackContract | None = None,
        source: str | None = None,
        definition_index: int | None = None,
    ) -> UserWord:
        self.validate_name(name)
        body_tokens = tuple(_coerce_token_text(token) for token in body)
        if not body_tokens:
            raise InvalidDefinition(
                "Definition body cannot be empty",
                context={"name": name},
            )

        dependencies: list[str] = []
        primitive_dependencies: list[str] = []
        dependency_set: set[str] = set()
        primitive_set: set[str] = set()

        for body_index, token in enumerate(body_tokens):
            if _is_literal(token):
                continue
            if token == name:
                raise RecursiveDefinition(
                    f"Recursive definition: {name}",
                    context={
                        "name": name,
                        "dependency": token,
                        "body_index": body_index,
                    },
                )
            resolved = self.resolve(token)
            if resolved is None:
                raise UnknownWord(
                    token,
                    index=body_index,
                    metadata={"definition": name},
                )
            if isinstance(resolved, Primitive):
                if token not in primitive_set:
                    primitive_dependencies.append(token)
                    primitive_set.add(token)
            else:
                if resolved.contract is None and contract is not None:
                    raise UnverifiableContract(
                        f"Dependency lacks contract: {token}",
                        context={"name": name, "dependency": token},
                    )
                if self._depends_on(resolved.name, name):
                    raise RecursiveDefinition(
                        f"Recursive definition: {name}",
                        context={"name": name, "dependency": resolved.name},
                    )
                if token not in dependency_set:
                    dependencies.append(token)
                    dependency_set.add(token)

        if contract is not None:
            self._validate_contracted_body(
                name=name,
                contract=contract,
                body_tokens=body_tokens,
            )

        return UserWord(
            name=name,
            body=body_tokens,
            dependencies=tuple(dependencies),
            primitive_dependencies=tuple(primitive_dependencies),
            contract=contract,
            source=source,
            definition_index=definition_index,
        )

    def define(self, word: UserWord) -> UserWord:
        self.validate_name(word.name)
        self._user_words[word.name] = word
        return word

    def _depends_on(self, name: str, target: str) -> bool:
        if name == target:
            return True
        entry = self._user_words.get(name)
        if entry is None:
            return False
        for dependency in entry.dependencies:
            if self._depends_on(dependency, target):
                return True
        return False

    def _validate_contracted_body(
        self,
        *,
        name: str,
        contract: StackContract,
        body_tokens: tuple[str, ...],
    ) -> None:
        observed = self._simulate_tokens(
            body_tokens,
            tuple(contract.inputs),
            visitor={name},
        )
        if len(observed) != len(contract.outputs):
            raise StaticContractViolation(
                f"Contract depth mismatch for {name}",
                context={
                    "name": name,
                    "expected": [kind.value for kind in contract.outputs],
                    "observed": [kind.value for kind in observed],
                },
            )
        for observed_kind, expected_kind in zip(
            observed,
            contract.outputs,
            strict=True,
        ):
            if expected_kind is ValueKind.ANY:
                continue
            if observed_kind is not expected_kind:
                raise StaticContractViolation(
                    f"Contract violation for {name}",
                    context={
                        "name": name,
                        "expected": [kind.value for kind in contract.outputs],
                        "observed": [kind.value for kind in observed],
                    },
                )

    def _simulate_tokens(
        self,
        tokens: tuple[str, ...],
        stack: tuple[ValueKind, ...],
        *,
        visitor: set[str],
    ) -> tuple[ValueKind, ...]:
        current = stack
        for token in tokens:
            if _is_literal(token):
                current = current + (_kind_from_literal(token),)
                continue
            resolved = self.resolve(token)
            if resolved is None:
                raise UnknownWord(token, index=-1)
            if isinstance(resolved, Primitive):
                try:
                    current = resolved.simulate(current)
                except TypeMismatch as error:
                    raise StaticContractViolation(
                        f"Contract violation for {resolved.name}",
                        context={
                            "name": resolved.name,
                            "primitive": resolved.name,
                            "observed": [kind.value for kind in current],
                        },
                    ) from error
                continue
            if resolved.contract is None:
                raise UnverifiableContract(
                    f"Dependency lacks contract: {token}",
                    context={"dependency": token},
                )
            if resolved.name in visitor:
                raise RecursiveDefinition(
                    f"Recursive definition: {resolved.name}",
                    context={"name": resolved.name},
                )
            visitor.add(resolved.name)
            try:
                current = self._simulate_tokens(
                    resolved.body,
                    current,
                    visitor=visitor,
                )
            finally:
                visitor.remove(resolved.name)
        return current


__all__ = ["Dictionary", "UserWord"]
