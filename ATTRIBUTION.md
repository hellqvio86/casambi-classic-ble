# Attribution and Acknowledgements

`casambi-classic-ble` is a specialized fork of [`casambi-bt`](https://github.com/lkempf/casambi-bt), originally created and authored by **Lukas Kempf** ([@lkempf](https://github.com/lkempf)).

The original `casambi-bt` repository established the foundational reverse-engineering, cryptographic handshake protocol, network state management, and BLE communication abstractions for Casambi networks in Python.

We are deeply grateful to Lukas Kempf and all contributors to upstream `casambi-bt` for their pioneering work on open-source Casambi integration.

---

## Relationship Between Upstream and This Fork

- **Upstream ([`lkempf/casambi-bt`](https://github.com/lkempf/casambi-bt)):**
  Primary focus is on modern Casambi **Evolution** firmware profile networks.
- **This Fork ([`hellqvio86/casambi-classic-ble`](https://github.com/hellqvio86/casambi-classic-ble)):**
  Dedicated specifically to legacy Casambi **Classic** firmware profile networks. It adapts GATT services (`0xFE3D`/`0xFE4D`), handles Classic cryptographic handshakes and passive advertisement frames (`0x03C3`/963), modernizes the codebase to Python 3.12+, and serves as the core BLE engine for the [`casambi-classic-bt-hass`](https://github.com/hellqvio86/casambi-classic-bt-hass) Home Assistant integration.

---

## Copyright and Licensing

Upstream `casambi-bt` is licensed under the Apache License, Version 2.0. Portions of this codebase derive from upstream `casambi-bt`:

- Copyright (c) Lukas Kempf and contributors
- Copyright (c) 2026 Olof Hellqvist (fork modifications and additions)

Licensed under the Apache License, Version 2.0 and/or MIT License. See [LICENSE](LICENSE) for details.
