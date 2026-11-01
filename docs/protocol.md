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

| Opcode | Name | Description | Payload Format | Status |
|---|---|---|---|---|
| `0x01` | `TURN_LIGHT_ON` | Direct power turn on | `[Unit ID (1B)]` | Observed, legacy (unexposed in high-level API) |
| `0x02` | `TURN_LIGHT_OFF` | Direct power turn off | `[Unit ID (1B)]` | Observed, legacy (unexposed in high-level API) |
| `0x03` | `SET_LEVEL` | Set brightness level / on / off | `[Unit ID (1B)] [Level (1B)]` or `[Unit ID (2B LE)] [Level (1B)]` | Standard power and dimming control |
| `0x04` | `SET_COLOR_TEMP` | Set Color Temperature (Kelvin) | `[Unit ID (1B)] [Temp Kelvin (2B LE)]` | Exposed via `set_color_temperature()` |
| `0x05` | `SET_RGB` | Set RGB channel levels | `[Unit ID (1B)] [R (1B)] [G (1B)] [B (1B)]` | Exposed via `set_rgb()` |
| `0x07` | `AUTHENTICATE` | Authenticate with network key | `[MD5 Password Hash (16B)]` | Exposed via `authenticate()` |
| `0x0F` | `GET_UNIT_STATE` | Query specific unit state | `[Unit ID (1B)]` | Used by `request_state()` |
| `0x10` | `GET_DEVICE_INFO` | Query device hardware info | *(Empty)* | Observed, not exposed (GATT DIS preferred) |
| `0x11` | `GET_NETWORK_INFO` | Query network configuration | *(Empty)* | Observed, not exposed |
| `0x14` | `GET_STATE` | Global query for unit states | `[Unit ID (1B)]` | Used by `request_state()` |
| `0x81` | `TURN_LIGHT_ON_LONG` | Direct power on by 6-byte address | `[Address (6B)]` | Exposed via `turn_on_by_address()` |
| `0x82` | `TURN_LIGHT_OFF_LONG` | Direct power off by 6-byte address | `[Address (6B)]` | Exposed via `turn_off_by_address()` |

---

## 3. Command Variant & Hardware Compatibility Matrix

Classic Casambi firmware supports multiple command payload variants depending on device firmware generation and channel topology. The table below details the exact payload structure, verified models, and capture provenance:

| Command | Opcode | Payload Variant | Payload Layout | Verified Hardware Models | Evidence | Notes |
|---|---|---|---|---|---|---|
| `turn_on` | `0x03` (`SET_LEVEL`) | 2-byte unit ID, level `0xFF` | `[Unit (2B LE)] [0xFF]` | Vadsbo LD220WCM, LD220WCM_onoff | Captured | Required by Classic firmware 26.x for reliable power toggle |
| `turn_off` | `0x03` (`SET_LEVEL`) | 2-byte unit ID, level `0x00` | `[Unit (2B LE)] [0x00]` | Vadsbo LD220WCM, LD220WCM_onoff | Captured | Required by Classic firmware 26.x for reliable power toggle |
| `set_level` (unit) | `0x03` (`SET_LEVEL`) | 1-byte unit ID, level `0x00..0xFF` | `[Unit (1B)] [Level (1B)]` | Vadsbo LD220WCM, CBU-PWM4 RGBW | Captured | Standard unit brightness adjustment |
| `set_level` (broadcast) | `0x03` (`SET_LEVEL`) | Broadcast unit `0xFFFF`, level `0x00..0xFF` | `[0xFF 0xFF] [Level (1B)]` | Vadsbo LD220WCM, LD220WCM_onoff | Derived | Broadcast brightness when `unit_id=None` |
| `turn_on_broadcast` | `0x03` (`SET_LEVEL`) | Broadcast unit `0xFFFF`, level `0xFF` | `[0xFF 0xFF] [0xFF]` | Vadsbo LD220WCM, LD220WCM_onoff | Derived | Targets all reachable units in mesh |
| `turn_off_broadcast` | `0x03` (`SET_LEVEL`) | Broadcast unit `0xFFFF`, level `0x00` | `[0xFF 0xFF] [0x00]` | Vadsbo LD220WCM, LD220WCM_onoff | Derived | Targets all reachable units in mesh |
| `turn_on_by_address` | `0x81` (`TURN_LIGHT_ON_LONG`) | 6-byte target MAC/address | `[MAC Address (6B)]` | Vadsbo LD220WCM | Captured | Direct unicast power on without mesh unit ID |
| `turn_off_by_address` | `0x82` (`TURN_LIGHT_OFF_LONG`) | 6-byte target MAC/address | `[MAC Address (6B)]` | Vadsbo LD220WCM | Captured | Direct unicast power off without mesh unit ID |
| `set_color_temperature` | `0x04` (`SET_COLOR_TEMP`) | 1-byte unit ID, 2-byte Kelvin LE | `[Unit (1B)] [Kelvin (2B LE)]` | AIMOTION GLOW | Captured | Tunable white / CCT control |
| `set_rgb` | `0x05` (`SET_RGB`) | 1-byte unit ID, 3-byte RGB | `[Unit (1B)] [R] [G] [B]` | Casambi CBU-PWM4 RGBW | Captured | 3-channel color control |
| `authenticate` | `0x07` (`AUTHENTICATE`) | 16-byte MD5 hash | `[MD5 Hash (16B)]` | All Classic Nodes | Captured | Optional password authorization |
| `request_state` | `0x14` (`GET_STATE`) & `0x0F` (`GET_UNIT_STATE`) | 1-byte unit ID | `[Unit (1B)]` | All Classic Nodes | Captured | Triggers unit status notification response |
| `TURN_LIGHT_ON` (Legacy) | `0x01` | 1-byte unit ID | `[Unit (1B)]` | Older Classic firmware | Derived | Observed alternate opcode, not used by `turn_on()` |
| `TURN_LIGHT_OFF` (Legacy) | `0x02` | 1-byte unit ID | `[Unit (1B)]` | Older Classic firmware | Derived | Observed alternate opcode, not used by `turn_off()` |
| `GET_DEVICE_INFO` | `0x10` | Empty | *(Empty)* | Classic firmware | Derived | Observed GATT control query; standard DIS (0x180A) preferred |
| `GET_NETWORK_INFO` | `0x11` | Empty | *(Empty)* | Classic firmware | Derived | Observed GATT control query |

---

## 4. Advertisement Beacon Format

Casambi devices broadcast passive BLE manufacturer data using Company Identifier `0x03C3` (decimal `963`, `CASAMBI_MANUFACTURER_ID`):

```
+------------------------------------+-------------------+-------------------+-----------------------------+
| Device MAC Address (Bytes 0..5)    | Status (Byte 6)   | Level (Byte 7)    | Trailing Flags (Bytes 8..N) |
+------------------------------------+-------------------+-------------------+-----------------------------+
```

### 4.1 Verified vs. Unverified Fields

To prevent misinterpreting undocumented mesh bits as user-visible state, the parser (`casambi_classic_ble._adv.parse_advertisement`) strictly separates **verified** fields from **unverified/inferred** fields:

| Byte Offset | Bit / Range | Field Name | Classification | Description |
|---|---|---|---|---|
| `0..5` | 48 bits | `reversed_mac` / `forward_mac` | **Verified** (`captured`) | 6-byte hardware MAC address, broadcast in reversed byte order (`[::-1]`) by Classic nodes. |
| `0` | 8 bits | `address_byte` | **Verified** (`captured`) | First raw byte of the manufacturer payload (least-significant MAC octet in reversed beacons). Never used as a unit `id`. |
| `6` | Bit 0 (`byte & 0x01`) | `is_on` (`on`) | **Verified** (`captured`) | Binary power state (`1` = On, `0` = Off). |
| `6` | Bits 1..7 (`(byte >> 1) & 0x7F`) | `unverified.status_flags` | **Unverified / Inferred** | 7-bit rolling sequence counter and internal status flags. Exposed only under `status["unverified"]["status_flags"]`. |
| `7` | `0x00`–`0xFF` | `level_byte` (`dimLevel`, `level_percent`) | **Verified** (`captured`) | Linear brightness level (`0x00` = 0%, `0xFF` = 100%). |
| `8..N` | 0..N bytes | `unverified.trailing_hex` | **Unverified / Inferred** | Optional network/unit mesh state bytes (`0` bytes in 8-byte minimal beacons, `2` bytes in standard 10-byte Classic 26.x beacons, `4+` bytes in extended 12-byte mesh beacons). Exposed only under `status["unverified"]["trailing_hex"]`. |

### 4.2 Supported Beacon Layouts & Validation Rules

1. **Manufacturer ID Validation:** Payloads from any Company ID other than `0x03C3` (`963`) are ignored (`None`).
2. **Minimum Length (`8` Bytes):** Frames shorter than 8 bytes lack the mandatory 6-byte MAC + 1-byte status + 1-byte level header and are safely ignored (`None`).
3. **Supported Frame Lengths:**
   - **8-byte minimal layout:** `[MAC (6B)] [Status (1B)] [Level (1B)]` (early Classic firmware).
   - **10-byte standard layout:** `[MAC (6B)] [Status (1B)] [Level (1B)] [Flags (2B)]` (Vadsbo LD220WCM, LD220WCM_onoff, Classic FW 26.x).
   - **12+ byte extended mesh layout:** `[MAC (6B)] [Status (1B)] [Level (1B)] [Mesh Trailing (4+B)]` (CBU-PWM4, AIMOTION GLOW).
4. **Cross-Device & Cross-Network Isolation:**
   - If a `BLEDevice` peripheral is supplied to `update_from_advertisement`, its address must match the `CasambiDevice` instance; frames originating from a different peripheral are rejected immediately.
   - Manufacturer payload MAC bytes (`0..5`) must also match the device's locked internal MAC or normalized target MAC, preventing relayed mesh frames from updating the wrong device.
5. **Duplicate Suppression & Counter Wraparound:**
   - State subscribers deduplicate consecutive identical `(on, dimLevel)` tuples per unit/device.
   - Rolling counter increments or 7-bit wraparound (`0x7F -> 0x00`, raw status byte `0xFE -> 0x00` or `0xFF -> 0x01`) and out-of-order advertisements never suppress a legitimate `(on, dimLevel)` state transition.

---

## 5. Cryptographic & Session Protocol Specification (`Casambi` Stack)

When utilizing the full network session controller (`Casambi` and `CasambiClientClassic`), communication uses challenge-response authentication and CMAC-signed frames over GATT. This section formalizes the cryptographic contract, packet layouts, and verification requirements.

### 5.1 Protocol Summary & Evidence Matrix

| Protocol Element | Specification / Invariant | Role / Scope | Evidence | Tested Models / Firmware |
|---|---|---|---|---|
| **Key Selection** | 16-byte AES-128 key from network key store | Visitor (`role = 2`) or Manager (`role = 3`) | `captured` | Vadsbo LD220WCM, Classic FW 26.x |
| **Password Hashing** | 16-byte MD5 digest of UTF-8 password | Unauthenticated GATT opcode `0x07` | `captured` | Classic Nodes (LD220WCM) |
| **Challenge Request** | OpCode `0x01` + 16-byte client random nonce | Session handshake initiation | `captured` | Classic FW 26.x |
| **Challenge Response** | OpCode `0x02` + 16-byte node nonce + version (1B) | Handshake confirmation & protocol negotiation | `captured` | Classic FW 26.x |
| **Protocol Version** | Integer `1`–`9` accepted; `>= 10` rejected | Classic firmware compatibility boundary | `captured` | Classic FW 26.x |
| **Connection Hash (`connhash`)** | Exactly 8 bytes derived from nonce exchange | Per-connection authentication context | `derived` | Classic Session Stack |
| **Cipher & Mode** | AES-128 in CMAC mode (RFC 4493 / NIST SP 800-38B) | Frame authentication & integrity | `derived` | Classic Session Stack |
| **CMAC Concatenation** | `CMAC(key, connhash [8B] + packet [NB])` | Input data order | `derived` | Classic Session Stack |
| **Signature Placement & Length** | Visitor: 4-byte prefix (`CMAC[:4]`); Manager: 16-byte prefix (`CMAC[:16]`) | Prepended to signed payload | `captured` | Classic FW 26.x |
| **Signature Comparison** | Constant-time comparison (`hmac.compare_digest`) | Side-channel timing defense | `derived` | Classic Session Stack |
| **Sequence Counter** | 1-byte counter (`0x00`–`0xFF`), increments per signed frame | Session anti-replay defense | `derived` | Classic Session Stack |
| **Session Teardown** | Sequence reset, session key clearance on disconnect | Session lifecycle management | `derived` | Classic Session Stack |

### 5.2 Key Derivation & Roles

- **Visitor Key (`role = 2`):** Used for standard control (level, scenes, unit state). Signatures are truncated to **4 bytes** (`sig_len = 4`).
- **Manager Key (`role = 3`):** Used for administrative mesh configuration. Signatures use full **16 bytes** (`sig_len = 16`).
- **Invariants:**
  - AES keys must be exactly 16 bytes (`len(key) == 16`). Invalid key lengths are rejected in `ClassicEncryptor.__init__`.
  - Signature length `sig_len` must be strictly `4` or `16`. Any other value raises a domain `ValueError`.

### 5.3 Challenge-Response Handshake

```
Client                                                  Node
  |                                                       |
  |--- OpCode 0x01 [Client Nonce (16B)] ----------------->| (Challenge Request)
  |<-- OpCode 0x02 [Node Nonce (16B)] [Version (1B)] -----| (Challenge Response)
  |                                                       |
```

1. **Challenge Request (`OpCode 0x01`):** Client generates a 16-byte cryptographically secure random nonce (`os.urandom(16)`) and writes it to the GATT Control characteristic.
2. **Challenge Response (`OpCode 0x02`):** Node responds via notification with its 16-byte nonce and a 1-byte protocol version number.
   - If `version < 1` or `version > 9`, connection is aborted immediately (Classic version mismatch / Evolution rejection).
3. **Connection Hash (`connhash`):** Derived from the nonce exchange. Must be exactly 8 bytes.

### 5.4 Signed Frame Construction & Verification

Packets sent to the GATT Control characteristic in signed session mode follow this byte structure:

```
+-----------------------------------+--------------------+--------------+-------------+---------------------+
| Truncated CMAC Signature (4B/16B) | Target Code (2B LE)| Opcode (1B)  | Seq No (1B) | Payload (N Bytes)   |
+-----------------------------------+--------------------+--------------+-------------+---------------------+
```

- **Digest Calculation:**
  ```python
  cmac = CMAC(AES(key))
  cmac.update(connhash + packet)
  signature = cmac.finalize()[:sig_len]
  signed_packet = signature + packet
  ```
- **Verification:**
  1. Verify packet length is at least `sig_len` bytes.
  2. Verify `connhash` is exactly 8 bytes.
  3. Recompute `expected_sig = CMAC(key).update(connhash + packet[sig_len:]).finalize()[:sig_len]`.
  4. Compare extracted `packet[:sig_len]` with `expected_sig` using constant-time `hmac.compare_digest`.
  5. If verification fails or packet is malformed, log an `ERROR` without disclosing raw key material or secret digests.

### 5.5 Sequence Counters & Anti-Replay Rules

- Each signed packet includes a 1-byte sequence counter (`Seq No`).
- Counter increments monotonically per transmitted frame (`(seq + 1) % 256`).
- On session termination or BLE disconnect, sequence counters are discarded. Re-authenticated sessions negotiate fresh nonces and reinitialize counters.

### 5.6 Authenticated vs Unauthenticated Packet Types

1. **Unauthenticated GATT Commands:**
   - Direct writes to Control Characteristic via `CasambiDevice`:
     - `0x01` / `0x02` (Turn On / Off legacy)
     - `0x03` (Set Level)
     - `0x04` (Set Color Temperature)
     - `0x05` (Set RGB)
     - `0x07` (Password Authentication MD5)
     - `0x0F` / `0x14` (Get State)
     - `0x81` / `0x82` (Turn On / Off by 6-byte address)
2. **Authenticated Session Packets (`CasambiClientClassic`):**
   - Packets wrapped in CMAC signed envelope with target code and sequence number.
   - Required for multi-unit networks, mesh broadcast forwarding, and state synchronization.

---

## 6. Capturing Protocol Frames with BTSnoop / Wireshark

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
