"""Casambi BLE exceptions hierarchy."""

from ._constants import ConnectionState


class CasambiError(Exception):
    """Base exception for Casambi BLE library."""

    pass


# Convenience alias for CasambiError
CasambiException = CasambiError


class CasambiClassicBleError(CasambiException):
    """Base class for all Casambi Classic BLE errors."""

    pass


# Backwards compatibility alias for casambi-bt
CasambiBtError = CasambiClassicBleError


class CasambiDeviceError(CasambiError):
    """Raised when device parameter or control command validation fails."""

    pass


class CasambiConnectionError(CasambiError):
    """Raised when connection fails."""

    pass


class CasambiCommandError(CasambiError):
    """Raised when a command fails."""

    pass


class CasambiDeviceNotFoundError(CasambiError):
    """Raised when device is not found during scanning."""

    pass


class CasambiCloudApiException(CasambiError):
    """Raised for errors in the Casambi Cloud API."""

    pass


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
    """Exception that is raised when authentication to the network fails."""

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


class BluetoothDeviceNotFoundError(CasambiDeviceNotFoundError, BluetoothError):
    """Exception that is raised when the bluetooth device used by the network can't be found."""

    pass


class ProtocolError(CasambiClassicBleError):
    """Exception that is raised when communication with the device doesn't follow the expected protocol."""

    pass


class UnsupportedProtocolVersion(CasambiClassicBleError):
    """Exception that is raised when the network has an unsupported version."""

    pass
