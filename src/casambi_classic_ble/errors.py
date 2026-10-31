"""Error types for Casambi Classic BLE."""

from ._constants import ConnectionState
from .exceptions import CasambiException


class CasambiClassicBleError(CasambiException):
    """Base class for all Casambi Classic BLE errors."""

    pass


# Backwards compatibility alias
CasambiBtError = CasambiClassicBleError


class NetworkNotFoundError(CasambiClassicBleError):
    """Exception that is raised when the network can't be found."""

    pass


class NetworkUpdateError(CasambiClassicBleError):
    """Exception that is raised when the network can't be updated."""

    pass


class NetworkOnlineUpdateNeededError(NetworkUpdateError):
    """Exception that is raised when an online update is needed for the network."""

    pass


class AuthenticationError(CasambiClassicBleError):
    """Excpetion that is raised when authentication to the network fails."""

    pass


class ConnectionStateError(CasambiClassicBleError):
    """Exception that is raised when the connection isn't in the required state."""

    def __init__(
        self,
        expected: ConnectionState,
        got: ConnectionState,
        expl: str | None = None,
    ) -> None:
        """Create a new `ConnectionStateError`."""
        self.expected = expected
        self.got = got

        msg = f"Expected state {expected.name}. Current state {got.name}."
        if expl:
            msg += " " + expl

        super().__init__(msg)


class BluetoothError(CasambiClassicBleError):
    """Exception that is raised when a bluetooth-related error happens."""

    pass


class BluetoothDeviceNotFoundError(CasambiClassicBleError):
    """Exception that is raised when the bluetooth device used by the network can't be found."""

    pass


class ProtocolError(CasambiClassicBleError):
    """Exception that is raised when communication with the device doesn't follow the expected protocol."""

    pass


class UnsupportedProtocolVersion(CasambiClassicBleError):
    """Exception that is raised when the network has an unsupported version."""

    pass
