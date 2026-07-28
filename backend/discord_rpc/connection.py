"""
Discord RPC Connection State Machine and Typed Exceptions.
"""

from enum import Enum
from typing import Dict, Set


class ConnectionState(Enum):
    DISCONNECTED = "DISCONNECTED"
    DISCOVERING = "DISCOVERING"
    CONNECTING = "CONNECTING"
    HANDSHAKING = "HANDSHAKING"
    READY = "READY"
    CLOSING = "CLOSING"
    FAILED = "FAILED"


# Valid state transitions
VALID_TRANSITIONS: Dict[ConnectionState, Set[ConnectionState]] = {
    ConnectionState.DISCONNECTED: {ConnectionState.DISCOVERING, ConnectionState.CONNECTING, ConnectionState.FAILED},
    ConnectionState.DISCOVERING: {ConnectionState.CONNECTING, ConnectionState.FAILED, ConnectionState.CLOSING},
    ConnectionState.CONNECTING: {ConnectionState.HANDSHAKING, ConnectionState.FAILED, ConnectionState.CLOSING},
    ConnectionState.HANDSHAKING: {ConnectionState.READY, ConnectionState.FAILED, ConnectionState.CLOSING},
    ConnectionState.READY: {ConnectionState.CLOSING, ConnectionState.FAILED},
    ConnectionState.CLOSING: {ConnectionState.DISCONNECTED, ConnectionState.FAILED},
    ConnectionState.FAILED: {ConnectionState.DISCONNECTED, ConnectionState.DISCOVERING, ConnectionState.CONNECTING},
}


class ConnectionError(Exception):
    """Base exception for RPC connection errors."""
    pass


class InvalidStateTransitionError(ConnectionError):
    """Raised when an illegal connection state transition is attempted."""
    def __init__(self, current_state: ConnectionState, target_state: ConnectionState):
        super().__init__(f"Invalid connection state transition from {current_state.value} to {target_state.value}")
        self.current_state = current_state
        self.target_state = target_state


class MissingClientIdError(ConnectionError):
    """Raised when no Application Client ID is configured."""
    pass


class SocketNotFoundError(ConnectionError):
    """Raised when no active Discord IPC socket could be discovered."""
    pass


class HandshakeFailedError(ConnectionError):
    """Raised when the handshake fails or returns an error."""
    pass


class TimeoutError(ConnectionError):
    """Raised when socket operations time out waiting for response."""
    pass


class SocketClosedError(ConnectionError):
    """Raised when socket receives EOF or CLOSE unexpectedly."""
    pass


class RPCCommandError(ConnectionError):
    """Raised when Discord RPC command returns an error payload."""
    def __init__(self, code: int, message: str):
        super().__init__(f"RPC Command Error [{code}]: {message}")
        self.code = code
        self.message = message


class UserDeniedError(RPCCommandError):
    """Raised when the user denies authorization in Discord UI."""
    def __init__(self, message: str = "User denied authorization prompt"):
        super().__init__(code=4009, message=message)


class ConnectionStateMachine:
    """Explicit state machine manager for Discord RPC connection lifecycle."""

    def __init__(self):
        self._state = ConnectionState.DISCONNECTED

    @property
    def state(self) -> ConnectionState:
        return self._state

    def transition_to(self, target: ConnectionState) -> None:
        """Attempt to transition to target state. Raises InvalidStateTransitionError if invalid."""
        if target not in VALID_TRANSITIONS.get(self._state, set()):
            raise InvalidStateTransitionError(self._state, target)
        self._state = target

    def reset(self) -> None:
        """Force reset state to DISCONNECTED."""
        self._state = ConnectionState.DISCONNECTED
