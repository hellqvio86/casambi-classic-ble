import warnings

import pytest

import casambi_classic_ble
from casambi_classic_ble._constants import ConnectionState
from casambi_classic_ble.exceptions import (
    AuthenticationError,
    BluetoothDeviceNotFoundError,
    BluetoothError,
    CasambiBtError,
    CasambiClassicBleError,
    CasambiCloudApiException,
    CasambiCommandError,
    CasambiConnectionError,
    CasambiDeviceError,
    CasambiDeviceNotFoundError,
    CasambiError,
    CasambiException,
    ConnectionStateError,
    NetworkNotFoundError,
    NetworkOnlineUpdateNeededError,
    NetworkUpdateError,
    ProtocolError,
    UnsupportedProtocolVersion,
)


def test_all_exceptions_exported_in_dunder_all():
    """Verify all exception classes are present in casambi_classic_ble.__all__."""
    expected_exceptions = [
        AuthenticationError,
        BluetoothDeviceNotFoundError,
        BluetoothError,
        CasambiBtError,
        CasambiClassicBleError,
        CasambiCloudApiException,
        CasambiCommandError,
        CasambiConnectionError,
        CasambiDeviceError,
        CasambiDeviceNotFoundError,
        CasambiError,
        CasambiException,
        ConnectionStateError,
        NetworkNotFoundError,
        NetworkOnlineUpdateNeededError,
        NetworkUpdateError,
        ProtocolError,
        UnsupportedProtocolVersion,
    ]
    for exc_cls in expected_exceptions:
        name = exc_cls.__name__
        assert name in casambi_classic_ble.__all__, f"{name} missing from __all__"
        assert getattr(casambi_classic_ble, name) is exc_cls


def test_bluetooth_device_not_found_hierarchy():
    """Verify BluetoothDeviceNotFoundError inherits from CasambiDeviceNotFoundError and BluetoothError."""
    err = BluetoothDeviceNotFoundError("Device not found")
    assert isinstance(err, CasambiDeviceNotFoundError)
    assert isinstance(err, BluetoothError)
    assert isinstance(err, CasambiError)
    assert isinstance(err, CasambiClassicBleError)


def test_connection_state_error_formatting():
    """Verify ConnectionStateError format string."""
    err = ConnectionStateError(
        expected=ConnectionState.AUTHENTICATED,
        got=ConnectionState.NONE,
        expl="Write attempted without auth",
    )
    assert err.expected == ConnectionState.AUTHENTICATED
    assert err.got == ConnectionState.NONE
    assert "Expected state AUTHENTICATED. Current state NONE. Write attempted without auth" in str(
        err
    )


def test_deprecated_errors_module_shim():
    """Verify errors.py emits deprecation warning and exports all error types."""
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        with pytest.deprecated_call():
            import importlib

            import casambi_classic_ble.errors

            importlib.reload(casambi_classic_ble.errors)

    from casambi_classic_ble.errors import (
        AuthenticationError as ErrAuth,
    )
    from casambi_classic_ble.errors import (
        BluetoothError as ErrBle,
    )
    from casambi_classic_ble.errors import (
        ProtocolError as ErrProto,
    )

    assert ErrAuth is AuthenticationError
    assert ErrBle is BluetoothError
    assert ErrProto is ProtocolError
