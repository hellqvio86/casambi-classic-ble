"""Casambi BLE exceptions"""


class CasambiError(Exception):
    """Base exception for Casambi BLE library"""

    pass


# Convenience alias for CasambiError
CasambiException = CasambiError


class CasambiDeviceError(CasambiError):
    """Raised when device parameter or control command validation fails"""

    pass


class CasambiConnectionError(CasambiError):
    """Raised when connection fails"""

    pass


class CasambiCommandError(CasambiError):
    """Raised when a command fails"""

    pass


class CasambiDeviceNotFoundError(CasambiError):
    """Raised when device is not found during scanning"""

    pass


class CasambiCloudApiException(CasambiError):
    """Raised for errors in the Casambi Cloud API"""

    pass
