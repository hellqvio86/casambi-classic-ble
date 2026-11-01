"""Tests verifying casambi_classic_ble core models and error types."""

from casambi_classic_ble import (
    Casambi,
    ColorSource,
    Group,
    Scene,
    Unit,
    UnitControlType,
    UnitState,
)
from casambi_classic_ble.exceptions import (
    AuthenticationError,
    BluetoothDeviceNotFoundError,
    BluetoothError,
    NetworkNotFoundError,
    ProtocolError,
)


def test_casambi_classic_ble_models() -> None:
    """Verify casambi_classic_ble classes are importable and exposed correctly."""
    assert Casambi is not None
    assert Group is not None
    assert Scene is not None
    assert Unit is not None
    assert UnitControlType is not None
    assert ColorSource is not None
    assert UnitState is not None


def test_casambi_classic_ble_errors() -> None:
    """Verify casambi_classic_ble exceptions exist."""
    assert issubclass(AuthenticationError, Exception)
    assert issubclass(BluetoothDeviceNotFoundError, Exception)
    assert issubclass(BluetoothError, Exception)
    assert issubclass(NetworkNotFoundError, Exception)
    assert issubclass(ProtocolError, Exception)
