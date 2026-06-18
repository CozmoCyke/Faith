from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


def _freeze_mapping(data: Mapping[str, Any] | None) -> Mapping[str, Any]:
    frozen = dict(sorted((data or {}).items()))
    return MappingProxyType(frozen)


class FaifthError(Exception):
    __slots__ = ("_code", "_message", "_metadata", "_context")

    default_code = "faifth.error"
    default_message = "Faifth error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        actual_message = self.default_message if message is None else message
        super().__init__(actual_message)
        self._code = self.default_code if code is None else code
        self._message = actual_message
        self._metadata = _freeze_mapping(metadata)
        self._context = _freeze_mapping(context)

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message

    @property
    def metadata(self) -> Mapping[str, Any]:
        return self._metadata

    @property
    def context(self) -> Mapping[str, Any]:
        return self._context

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "metadata": dict(self.metadata),
            "context": dict(self.context),
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r}, "
            f"metadata={dict(self.metadata)!r}, context={dict(self.context)!r})"
        )

    def __eq__(self, other: object) -> bool:
        if other.__class__ is not self.__class__:
            return False
        assert isinstance(other, FaifthError)
        return (
            self.code == other.code
            and self.message == other.message
            and dict(self.metadata) == dict(other.metadata)
            and dict(self.context) == dict(other.context)
        )


class StackUnderflow(FaifthError):
    default_code = "faifth.stack_underflow"
    default_message = "Stack underflow"


class StackOverflow(FaifthError):
    default_code = "faifth.stack_overflow"
    default_message = "Stack overflow"


class TypeMismatch(FaifthError):
    default_code = "faifth.type_mismatch"
    default_message = "Type mismatch"


class InvalidValue(FaifthError):
    default_code = "faifth.invalid_value"
    default_message = "Invalid value"


class InvalidSnapshot(FaifthError):
    default_code = "faifth.invalid_snapshot"
    default_message = "Invalid snapshot"


class InvalidContract(FaifthError):
    default_code = "faifth.invalid_contract"
    default_message = "Invalid contract"


class MalformedContract(FaifthError):
    default_code = "faifth.malformed_contract"
    default_message = "Malformed contract"


class UnknownContractType(FaifthError):
    default_code = "faifth.unknown_contract_type"
    default_message = "Unknown contract type"


class ContractInputMismatch(TypeMismatch):
    default_code = "faifth.contract_input_mismatch"
    default_message = "Contract input mismatch"


class ContractOutputMismatch(TypeMismatch):
    default_code = "faifth.contract_output_mismatch"
    default_message = "Contract output mismatch"


class ContractDepthMismatch(StackUnderflow):
    default_code = "faifth.contract_depth_mismatch"
    default_message = "Contract depth mismatch"


class UnverifiableContract(FaifthError):
    default_code = "faifth.unverifiable_contract"
    default_message = "Unverifiable contract"


class StaticContractViolation(FaifthError):
    default_code = "faifth.static_contract_violation"
    default_message = "Static contract violation"


class InvalidBudget(FaifthError):
    default_code = "faifth.invalid_budget"
    default_message = "Invalid budget"


class InvalidCapability(FaifthError):
    default_code = "faifth.invalid_capability"
    default_message = "Invalid capability"


class BudgetExceeded(FaifthError):
    default_code = "faifth.budget_exceeded"
    default_message = "Budget exceeded"


class StepBudgetExceeded(BudgetExceeded):
    default_code = "faifth.step_budget_exceeded"
    default_message = "Step budget exceeded"


class StackDepthBudgetExceeded(BudgetExceeded):
    default_code = "faifth.stack_depth_budget_exceeded"
    default_message = "Stack depth budget exceeded"


class UnknownWord(FaifthError):
    default_code = "faifth.unknown_word"
    default_message = "Unknown word"

    def __init__(
        self,
        word: str,
        *,
        index: int,
        line: int | None = None,
        column: int | None = None,
        offset: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        context: dict[str, Any] = {"word": word, "index": index}
        if line is not None:
            context["line"] = line
        if column is not None:
            context["column"] = column
        if offset is not None:
            context["offset"] = offset
        super().__init__(
            f"Unknown word: {word}",
            metadata=metadata,
            context=context,
        )


class InvalidDefinition(FaifthError):
    default_code = "faifth.invalid_definition"
    default_message = "Invalid definition"


class DuplicateWord(FaifthError):
    default_code = "faifth.duplicate_word"
    default_message = "Duplicate word"


class ProtectedWord(FaifthError):
    default_code = "faifth.protected_word"
    default_message = "Protected word"


class UnterminatedDefinition(FaifthError):
    default_code = "faifth.unterminated_definition"
    default_message = "Unterminated definition"


class UnexpectedTerminator(FaifthError):
    default_code = "faifth.unexpected_terminator"
    default_message = "Unexpected terminator"


class RecursiveDefinition(FaifthError):
    default_code = "faifth.recursive_definition"
    default_message = "Recursive definition"


class CallDepthExceeded(BudgetExceeded):
    default_code = "faifth.call_depth_exceeded"
    default_message = "Call depth exceeded"


class CapabilityDenied(FaifthError):
    default_code = "faifth.capability_denied"
    default_message = "Capability denied"


class CapabilityEscalationDenied(FaifthError):
    default_code = "faifth.capability_escalation_denied"
    default_message = "Capability escalation denied"


class InterpreterError(FaifthError):
    default_code = "faifth.interpreter_error"
    default_message = "Interpreter error"


class TransactionAlreadyActive(FaifthError):
    default_code = "faifth.transaction_already_active"
    default_message = "Transaction already active"


class NoActiveTransaction(FaifthError):
    default_code = "faifth.no_active_transaction"
    default_message = "No active transaction"


class TransactionCommitError(FaifthError):
    default_code = "faifth.transaction_commit_error"
    default_message = "Transaction commit error"


class TransactionRollbackError(FaifthError):
    default_code = "faifth.transaction_rollback_error"
    default_message = "Transaction rollback error"


class PersistenceError(FaifthError):
    default_code = "faifth.persistence_error"
    default_message = "Persistence error"


class StoragePermissionDenied(PersistenceError):
    default_code = "faifth.storage_permission_denied"
    default_message = "Storage permission denied"


class StorageIntegrityError(PersistenceError):
    default_code = "faifth.storage_integrity_error"
    default_message = "Storage integrity error"


class UnsupportedSchemaVersion(PersistenceError):
    default_code = "faifth.unsupported_schema_version"
    default_message = "Unsupported schema version"


class CorruptWordVersion(PersistenceError):
    default_code = "faifth.corrupt_word_version"
    default_message = "Corrupt word version"


class MissingWordVersion(PersistenceError):
    default_code = "faifth.missing_word_version"
    default_message = "Missing word version"


class MissingDependency(PersistenceError):
    default_code = "faifth.missing_dependency"
    default_message = "Missing dependency"


class DependencyCycle(PersistenceError):
    default_code = "faifth.dependency_cycle"
    default_message = "Dependency cycle"


class RestoreValidationError(PersistenceError):
    default_code = "faifth.restore_validation_error"
    default_message = "Restore validation error"


class ActiveVersionError(PersistenceError):
    default_code = "faifth.active_version_error"
    default_message = "Active version error"


class ProtocolError(FaifthError):
    default_code = "faifth.protocol_error"
    default_message = "Protocol error"


class InvalidRequest(ProtocolError):
    default_code = "faifth.invalid_request"
    default_message = "Invalid request"


class UnsupportedProtocolVersion(ProtocolError):
    default_code = "faifth.unsupported_protocol_version"
    default_message = "Unsupported protocol version"


class UnknownAction(ProtocolError):
    default_code = "faifth.unknown_action"
    default_message = "Unknown action"


class UnknownSession(ProtocolError):
    default_code = "faifth.unknown_session"
    default_message = "Unknown session"


class SessionAlreadyExists(ProtocolError):
    default_code = "faifth.session_already_exists"
    default_message = "Session already exists"


class RequestIdConflict(ProtocolError):
    default_code = "faifth.request_id_conflict"
    default_message = "Request id conflict"


class InvalidArguments(ProtocolError):
    default_code = "faifth.invalid_arguments"
    default_message = "Invalid arguments"


class UnknownCandidate(ProtocolError):
    default_code = "faifth.unknown_candidate"
    default_message = "Unknown candidate"


class CandidateHashMismatch(ProtocolError):
    default_code = "faifth.candidate_hash_mismatch"
    default_message = "Candidate hash mismatch"


class CandidateNotTested(ProtocolError):
    default_code = "faifth.candidate_not_tested"
    default_message = "Candidate not tested"


class CandidateTestsFailed(ProtocolError):
    default_code = "faifth.candidate_tests_failed"
    default_message = "Candidate tests failed"


class CandidateStale(ProtocolError):
    default_code = "faifth.candidate_stale"
    default_message = "Candidate stale"


class UnknownRepository(ProtocolError):
    default_code = "faifth.unknown_repository"
    default_message = "Unknown repository"


class ProtocolLimitExceeded(ProtocolError):
    default_code = "faifth.protocol_limit_exceeded"
    default_message = "Protocol limit exceeded"


__all__ = [
    "FaifthError",
    "StackUnderflow",
    "StackOverflow",
    "TypeMismatch",
    "InvalidValue",
    "InvalidSnapshot",
    "InvalidContract",
    "MalformedContract",
    "UnknownContractType",
    "ContractInputMismatch",
    "ContractOutputMismatch",
    "ContractDepthMismatch",
    "UnverifiableContract",
    "StaticContractViolation",
    "InvalidBudget",
    "InvalidCapability",
    "BudgetExceeded",
    "StepBudgetExceeded",
    "StackDepthBudgetExceeded",
    "UnknownWord",
    "CapabilityDenied",
    "CapabilityEscalationDenied",
    "InvalidDefinition",
    "DuplicateWord",
    "ProtectedWord",
    "UnterminatedDefinition",
    "UnexpectedTerminator",
    "RecursiveDefinition",
    "CallDepthExceeded",
    "InterpreterError",
    "TransactionAlreadyActive",
    "NoActiveTransaction",
    "TransactionCommitError",
    "TransactionRollbackError",
    "PersistenceError",
    "StoragePermissionDenied",
    "StorageIntegrityError",
    "UnsupportedSchemaVersion",
    "CorruptWordVersion",
    "MissingWordVersion",
    "MissingDependency",
    "DependencyCycle",
    "RestoreValidationError",
    "ActiveVersionError",
    "ProtocolError",
    "InvalidRequest",
    "UnsupportedProtocolVersion",
    "UnknownAction",
    "UnknownSession",
    "SessionAlreadyExists",
    "RequestIdConflict",
    "InvalidArguments",
    "UnknownCandidate",
    "CandidateHashMismatch",
    "CandidateNotTested",
    "CandidateTestsFailed",
    "CandidateStale",
    "UnknownRepository",
    "ProtocolLimitExceeded",
]
