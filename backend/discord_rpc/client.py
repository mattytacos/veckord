"""
Discord RPC Client module.

Manages Unix domain socket connection, protocol framing, state transitions,
nonce-correlated command execution, and initial HANDSHAKE / READY event sequence.
"""

import os
import uuid
import socket
import select
import logging
from typing import Any, Dict, List, Optional

from backend.discord_rpc.connection import (
    ConnectionState,
    ConnectionStateMachine,
    ConnectionError,
    MissingClientIdError,
    SocketNotFoundError,
    HandshakeFailedError,
    TimeoutError as RPCTimeoutError,
    SocketClosedError,
    RPCCommandError,
    UserDeniedError,
)
from backend.discord_rpc.discovery import get_active_ipc_socket
from backend.discord_rpc.protocol import (
    Opcode,
    ParsedFrame,
    FrameParser,
    encode_frame,
    ProtocolError,
)

logger = logging.getLogger(__name__)


class DiscordRPCClient:
    """
    Client for interacting with Discord local RPC over Unix sockets.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        socket_path: Optional[str] = None,
        timeout: float = 5.0,
    ):
        self.client_id = client_id or os.environ.get("VECKORD_DISCORD_CLIENT_ID")
        self.specified_socket_path = socket_path
        self.selected_socket_path: Optional[str] = None
        self.timeout = timeout

        self.state_machine = ConnectionStateMachine()
        self.parser = FrameParser()
        self._frame_queue: List[ParsedFrame] = []
        self._unmatched_frames: List[ParsedFrame] = []
        self._socket: Optional[socket.socket] = None
        self.rpc_version: Optional[int] = None
        self.user_data: Optional[Dict[str, Any]] = None

    @property
    def state(self) -> ConnectionState:
        return self.state_machine.state

    def connect_and_handshake(self) -> Dict[str, Any]:
        """
        Execute socket connection and RPC HANDSHAKE sequence until READY event is received.
        """
        if not self.client_id:
            raise MissingClientIdError("No Discord Application Client ID configured (VECKORD_DISCORD_CLIENT_ID).")

        try:
            # 1. Discover socket
            if self.state != ConnectionState.DISCONNECTED:
                self.close()

            self.state_machine.transition_to(ConnectionState.DISCOVERING)

            if self.specified_socket_path:
                self.selected_socket_path = self.specified_socket_path
            else:
                active_meta = get_active_ipc_socket()
                if not active_meta or not active_meta.can_connect:
                    raise SocketNotFoundError("No active, connectable Discord IPC socket found on system.")
                self.selected_socket_path = active_meta.path

            # 2. Connect socket
            self.state_machine.transition_to(ConnectionState.CONNECTING)
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            
            try:
                self._socket.connect(self.selected_socket_path)
            except (socket.timeout, TimeoutError):
                raise RPCTimeoutError(f"Connection timeout connecting to socket {self.selected_socket_path}")
            except Exception as e:
                raise ConnectionError(f"Failed to connect to socket {self.selected_socket_path}: {e}") from e

            # 3. Handshake
            self.state_machine.transition_to(ConnectionState.HANDSHAKING)
            handshake_payload = {
                "v": 1,
                "client_id": str(self.client_id),
            }
            frame_bytes = encode_frame(Opcode.HANDSHAKE, handshake_payload)
            self._socket.sendall(frame_bytes)

            # 4. Wait for READY event frame
            ready_payload = self._wait_for_ready_event()
            
            # Extract RPC version and user data safely
            self.rpc_version = ready_payload.get("v", 1) if isinstance(ready_payload, dict) else 1
            if isinstance(ready_payload, dict) and "data" in ready_payload:
                data_dict = ready_payload["data"]
                if isinstance(data_dict, dict):
                    self.user_data = data_dict.get("user")
                    if isinstance(data_dict.get("v"), int):
                        self.rpc_version = data_dict["v"]

            self.state_machine.transition_to(ConnectionState.READY)
            logger.info(f"Discord RPC Handshake successful (Socket: {self.selected_socket_path}, RPC Version: {self.rpc_version})")
            return ready_payload

        except Exception as e:
            self._fail_and_close()
            if isinstance(e, ConnectionError):
                raise
            raise ConnectionError(f"Handshake failed: {e}") from e

    def send_command(
        self,
        cmd: str,
        args: Optional[Dict[str, Any]] = None,
        evt: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Send a nonce-correlated RPC command and wait for matching response frame.
        """
        if self.state != ConnectionState.READY:
            raise ConnectionError(f"Cannot send command '{cmd}': client is in state {self.state.value}, expected READY.")

        nonce = str(uuid.uuid4())
        payload: Dict[str, Any] = {
            "cmd": cmd,
            "nonce": nonce,
        }
        if args is not None:
            payload["args"] = args
        if evt is not None:
            payload["evt"] = evt

        self.send_frame(Opcode.FRAME, payload)
        return self._read_command_response(nonce, timeout=timeout)

    def read_frame(self, timeout: Optional[float] = None) -> ParsedFrame:
        """
        Read the next complete frame from socket. Handles PING auto-PONG response.
        """
        if not self._socket:
            raise SocketClosedError("Socket is not connected.")

        effective_timeout = self.timeout if timeout is None else timeout
        self._socket.settimeout(effective_timeout)

        while True:
            if self._frame_queue:
                frame = self._frame_queue.pop(0)
                return self._handle_incoming_frame(frame)

            # Read chunk from socket
            try:
                chunk = self._socket.recv(4096)
            except (socket.timeout, TimeoutError):
                raise RPCTimeoutError(f"Socket read timed out after {effective_timeout}s.")
            except Exception as e:
                raise SocketClosedError(f"Socket read error: {e}") from e

            if not chunk:
                raise SocketClosedError("Socket received EOF (connection closed by server).")

            try:
                parsed_frames = self.parser.feed(chunk)
                if parsed_frames:
                    self._frame_queue.extend(parsed_frames)
            except ProtocolError as e:
                raise HandshakeFailedError(f"Protocol error during frame parsing: {e}") from e

    def send_frame(self, opcode: Opcode, payload: Any = None) -> None:
        """
        Encode and transmit a frame over the connected socket.
        """
        if not self._socket:
            raise SocketClosedError("Cannot send frame: socket is not connected.")
        frame_bytes = encode_frame(opcode, payload)
        try:
            self._socket.sendall(frame_bytes)
        except Exception as e:
            raise SocketClosedError(f"Failed to send frame over socket: {e}") from e

    def _read_command_response(self, nonce: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Read frames until frame with matching nonce is returned.
        Unrelated frames are stashed in _unmatched_frames.
        """
        effective_timeout = self.timeout if timeout is None else timeout
        
        # First check if matching nonce is already in unmatched frames
        for i, frame in enumerate(self._unmatched_frames):
            if isinstance(frame.payload, dict) and frame.payload.get("nonce") == nonce:
                self._unmatched_frames.pop(i)
                return self._process_command_response_payload(frame.payload)

        while True:
            frame = self.read_frame(timeout=effective_timeout)
            
            if frame.opcode == Opcode.CLOSE:
                msg = frame.payload.get("message") if isinstance(frame.payload, dict) else "Closed by server"
                raise SocketClosedError(f"Server sent CLOSE frame while waiting for command response: {msg}")

            if frame.opcode == Opcode.FRAME and isinstance(frame.payload, dict):
                resp_nonce = frame.payload.get("nonce")
                if resp_nonce == nonce:
                    return self._process_command_response_payload(frame.payload)
                else:
                    # Unrelated event or frame for a different nonce - keep in unmatched queue
                    self._unmatched_frames.append(frame)

    def _process_command_response_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate command response payload and raise typed RPC errors if present.
        """
        cmd = payload.get("cmd")
        evt = payload.get("evt")

        if evt == "ERROR" or cmd == "ERROR":
            data = payload.get("data", {})
            code = data.get("code", 0) if isinstance(data, dict) else 0
            message = data.get("message", "RPC Error") if isinstance(data, dict) else str(data)

            if code == 4009 or "denied" in message.lower() or "cancel" in message.lower():
                raise UserDeniedError(message)

            raise RPCCommandError(code, message)

        return payload

    def _wait_for_ready_event(self) -> Dict[str, Any]:
        """
        Read frames until a valid READY event frame is received.
        """
        start_time = self.timeout
        while True:
            frame = self.read_frame(timeout=start_time)
            
            if frame.opcode == Opcode.CLOSE:
                msg = frame.payload.get("message") if isinstance(frame.payload, dict) else "Closed by server"
                raise SocketClosedError(f"Server sent CLOSE frame before READY: {msg}")

            if frame.opcode == Opcode.FRAME:
                payload = frame.payload
                if isinstance(payload, dict):
                    cmd = payload.get("cmd")
                    evt = payload.get("evt")
                    
                    if evt == "READY" or (cmd == "DISPATCH" and evt == "READY"):
                        return payload

                    if evt == "ERROR" or cmd == "ERROR":
                        err_msg = payload.get("data", {}).get("message", "Unknown RPC Error")
                        raise HandshakeFailedError(f"Discord RPC returned ERROR event: {err_msg}")

                raise HandshakeFailedError(f"Unexpected frame payload before READY: {payload!r}")

    def _handle_incoming_frame(self, frame: ParsedFrame) -> ParsedFrame:
        """
        Process incoming frame, auto-responding to PING with PONG.
        """
        if frame.opcode == Opcode.PING:
            logger.debug("Received PING frame, sending PONG response.")
            self.send_frame(Opcode.PONG, frame.payload)

        return frame

    def _fail_and_close(self) -> None:
        """
        Transition state machine to FAILED and clean up socket resources.
        """
        if self.state not in (ConnectionState.DISCONNECTED, ConnectionState.FAILED):
            try:
                self.state_machine.transition_to(ConnectionState.FAILED)
            except Exception:
                self.state_machine.reset()
                self.state_machine.transition_to(ConnectionState.FAILED)
        self._cleanup_socket()

    def close(self) -> None:
        """
        Gracefully close connection and reset state machine to DISCONNECTED. Idempotent.
        """
        if self.state in (ConnectionState.DISCONNECTED, ConnectionState.FAILED):
            self._cleanup_socket()
            self.state_machine.reset()
            return

        try:
            self.state_machine.transition_to(ConnectionState.CLOSING)
        except Exception:
            pass

        self._cleanup_socket()
        self.state_machine.reset()

    def _cleanup_socket(self) -> None:
        """
        Shutdown and close socket object safely.
        """
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self.parser.clear()
        self._frame_queue.clear()
        self._unmatched_frames.clear()
