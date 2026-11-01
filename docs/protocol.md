# Casambi Classic BLE Protocol Specification

This document details the Bluetooth Low Energy (BLE) protocol format used by Casambi Classic firmware devices, including service UUIDs, characteristic layouts, opcode assignments, frame formats, and packet sniffing procedures.

---

## 1. Services & Characteristic UUIDs

Casambi devices expose GATT services for control and status notifications. Classic networks commonly utilize one of two service variants (`FE3D` or `FE4D`):

### Variant 1 (FE3D Service)
- **Primary Service UUID:** `0000fe3d-0000-1000-8000-00805f9b34fb`
- **Control Characteristic:** `0000fe3e-0000-1000-8000-00805f9b34fb` (Write with response)
- **Status Characteristic:** `0000fe3f-0000-1000-8000-00805f9b34fb` (Notify)

### Variant 2 (FE4D Service - Most Common)
- **Primary Service UUID:** `0000fe4d-0000-1000-8000-00805f9b34fb`
- **Control Characteristic:** `c9ffde48-ca5a-0001-ab83-8f519b482f77` (Write with response)
- **Status Characteristic:** `c9ffde48-ca5a-0002-ab83-8f519b482f77` (Notify)

### Standard Device Information Service (DIS)
- **Service UUID:** `0000180a-0000-1000-8000-00805f9b34fb`
- **Manufacturer Name:** `00002a29-0000-1000-8000-00805f9b34fb`
- **Model Number:** `00002a24-0000-1000-8000-00805f9b34fb`
- **Firmware Revision:** `00002a26-0000-1000-8000-00805f9b34fb`

---

## 2. Command Frame Format & Opcode Table

Packets written to the Control Characteristic begin with a 1-byte command opcode followed by an unencrypted payload:

```
+---------------+-----------------------------------------------+
| Opcode (1B)   | Payload (N Bytes, little-endian)              |
+---------------+-----------------------------------------------+
```

### Supported Opcodes (`CasambiCommands`)

| Opcode | Name | Description | Payload Format |
|---|---|---|---|
| `0x01` | `TURN_LIGHT_ON` | Direct power turn on | `[Unit ID (1B)]` |
| `0x02` | `TURN_LIGHT_OFF` | Direct power turn off | `[Unit ID (1B)]` |
| `0x03` | `SET_LEVEL` | Set brightness level / on / off | `[Unit ID (1B)] [Level (1B)]` or `[Unit ID (2B LE)] [Level (1B)]` |
| `0x04` | `SET_COLOR_TEMP` | Set Color Temperature (Kelvin) | `[Unit ID (1B)] [Temp Kelvin (2B LE)]` |
| `0x05` | `SET_RGB` | Set RGB channel levels | `[Unit ID (1B)] [R (1B)] [G (1B)] [B (1B)]` |
| `0x07` | `AUTHENTICATE` | Authenticate with network key | `[MD5 Password Hash (16B)]` |
| `0x0F` | `GET_UNIT_STATE` | Query specific unit state | `[Unit ID (1B)]` |
| `0x10` | `GET_DEVICE_INFO` | Query device hardware info | *(Empty)* |
| `0x11` | `GET_NETWORK_INFO` | Query network configuration | *(Empty)* |
| `0x14` | `GET_STATE` | Global query for unit states | `[Unit ID (1B)]` |

---

## 3. Advertisement Beacon Format

Casambi devices broadcast passive BLE manufacturer data using Company Identifier `0x03C3` (decimal `963`):

```
+------------------------------------+-----------------------------+
| Device MAC Address (6 Bytes, rev)  | Status / Flags (4 Bytes)    |
+------------------------------------+-----------------------------+
```

- Byte 0..5: 6-byte hardware device address (often transmitted in reversed byte order by Classic nodes).
- Byte 6..9: Rolling counter, network state, and unit status flags.

---

## 4. Capturing Protocol Frames with BTSnoop / Wireshark

To capture and inspect live frames for new devices or test fixtures:

### Method A: Android BTSnoop HCI Log (Recommended)
1. Enable **Developer Options** on your Android smartphone.
2. In Developer Options, enable **Enable Bluetooth HCI snoop log**.
3. Toggle Bluetooth off and on.
4. Open the official Casambi app and execute the target command (e.g., toggle light, adjust dimmer).
5. Extract the BTSnoop log via ADB:
   ```bash
   adb bugreport btsnoop_capture
   # or pull the file directly:
   adb pull /sdcard/btsnoop_hci.log btsnoop.log
   ```
6. Open `btsnoop.log` in **Wireshark**.
7. Filter by Casambi characteristic:
   ```
   btatt.handle or btgatt
   ```
8. Locate `Write Command` or `Write Request` packets sent to handle corresponding to `c9ffde48-ca5a-0001-...`.

### Method B: Linux `btmon`
1. On a Linux host with a BLE adapter, run:
   ```bash
   sudo btmon -w casambi_capture.pcap
   ```
2. In another terminal, connect and send commands via `casambi-classic-ble` or `gatttool`.
3. Stop `btmon` (Ctrl+C) and inspect `casambi_capture.pcap` in Wireshark.

> [!CAUTION]
> Always sanitize captured frames before submitting as fixtures: replace real network passwords, MAC addresses, and cryptographic keys with mock placeholders (`AA:BB:CC:DD:EE:FF` or `aabbccddeeff`).
