# ruff: noqa: E402, I001
"""Phase 4 capability tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faifth import Capability, CapabilitySet, InvalidCapability


def test_capability_set_is_immutable_and_sorted() -> None:
    caps = CapabilitySet.of("transaction.manage", "core.stack", "core.compute")

    assert caps.to_tuple() == ("core.compute", "core.stack", "transaction.manage")
    assert caps.to_dict() == {
        "granted": ["core.compute", "core.stack", "transaction.manage"],
    }


def test_capability_set_supports_set_operations() -> None:
    left = CapabilitySet.of("core.compute", "core.stack")
    right = CapabilitySet.of("core.stack", "dictionary.define")

    assert left.allows(CapabilitySet.of("core.stack"))
    assert left.missing(right).to_tuple() == ("dictionary.define",)
    assert left.union(right).to_tuple() == (
        "core.compute",
        "core.stack",
        "dictionary.define",
    )
    assert left.intersection(right).to_tuple() == ("core.stack",)
    assert left.difference(right).to_tuple() == ("core.compute",)


def test_capability_validation_is_structured() -> None:
    with pytest.raises(InvalidCapability):
        Capability("")

    with pytest.raises(InvalidCapability):
        CapabilitySet.of("bad capability")


def test_development_defaults_include_phase_4_compatibility_caps() -> None:
    caps = CapabilitySet.development_defaults()

    assert caps.allows(
        CapabilitySet.of(
            "core.compute",
            "core.stack",
            "dictionary.define",
            "transaction.manage",
        )
    )
