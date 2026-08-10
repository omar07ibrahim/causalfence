"""Public exception types."""


class CausalFenceError(ValueError):
    """Base class for expected CausalFence failures."""


class ContractError(CausalFenceError):
    """Raised when an input trace violates the bounded contract."""


class VerificationError(CausalFenceError):
    """Raised when a receipt cannot be independently reproduced."""
