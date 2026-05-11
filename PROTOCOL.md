# LIN Bus Protocol Findings

Reverse engineering notes for the iDrive/LIN protocol used between the IKEA Mittzon standing desk's ROL Group controller and handset panel.

## Bus characteristics

- **Baud rate:** 19200
- **Format:** 8N1
- **Physical layer:** Single-wire LIN-like bus on RJ45 pin 3
- **Topology:** Multi-master (controller + panel both transmit)
- **Frame structure:** BREAK + SYNC (0x55) + PID + response bytes

## PID schedule

The master (controller) continuously polls 12 PIDs in a cyclic schedule:

| PID | Approx. rate | Notes |
|---|---|---|
| 0x03 | ~10/s | Unknown payload |
| 0x06 | ~10/s | Unknown payload |
| 0x08 | ~10/s | Position data (encoder ticks) |
| 0x11 | ~10/s | Constant response |
| 0x42 | ~10/s | Unknown payload |
| 0x47 | ~10/s | Unknown payload |
| 0x50 | **~70/s** | High-frequency filler/keepalive |
| 0x80 | ~10/s | Constant response |
| 0x85 | ~10/s | Unknown payload |
| 0x92 | ~10/s | Movement state + position |
| 0xC1 | ~10/s | Unknown payload |
| 0xC4 | ~10/s | Unknown payload |

Total bus utilization: ~190 frames/second.

## Decoded responses

### PID 0x80 — Constant

- **Payload:** `0x00 0x00 0x00 0x7F` (4 bytes)
- **Checksum:** Matches LIN enhanced checksum for PID 0x80
- Always the same value, likely a status register or capability advertisement

### PID 0x11 — Constant

- **Payload:** `0x00 0xEE` (2 bytes)
- **Checksum:** Matches LIN enhanced checksum for PID 0x11
- Static, unknown purpose

### PID 0x92 — Movement state (panel → controller)

The most interesting PID. This is the panel telling the controller what the user is doing.

- **Idle:** `0x05 0x94 0xFE` (3 bytes)
- **UP pressed:** `0x0A` (1 byte)
- **DOWN pressed:** Not captured (panel was silent during DOWN in our sigrok sessions)

**Byte 0** encodes the button state:
| Value | Meaning |
|---|---|
| 0x05 | Idle (no button pressed) |
| 0x0A | UP button pressed |
| 0x44 | Observed during settling |
| 0x00 | Observed during transitions |

The trailing bytes in the idle response (`0x94 0xFE`) do not match any standard LIN checksum algorithm (see below).

### PID 0x08 — Position data

- **Payload:** 2-4 bytes, variable length
- **Bytes [2:3]** (when present): Little-endian uint16 = encoder ticks
- Position range observed: ~888 (lowest) to ~6669 (highest)
- Calibration: 102.93 ticks/cm, zero offset 60.29 cm

## Checksum analysis

Standard LIN defines two checksum variants:
- **Classic checksum:** Sum of data bytes + carry folding, inverted
- **Enhanced checksum:** Same, but includes the PID in the sum

Results across PIDs:

| PID | Classic match | Enhanced match | Notes |
|---|---|---|---|
| 0x80 | No | **Yes** | 4-byte constant response |
| 0x11 | No | **Yes** | 2-byte constant response |
| 0x92 | No | No | **iDrive proprietary** |
| 0x08 | Partial | Partial | Some frames match, others don't |

The iDrive protocol appears to use enhanced checksums for some PIDs but a proprietary algorithm for others (notably 0x92). We did not crack the proprietary checksum.

## Capture methodology

- **Tool:** sigrok-cli with a 24MHz/4MHz USB logic analyzer on Mac M1
- **Decoder:** Custom Python script (`scripts/sigrok-decode.py`) with BREAK detection, SYNC validation, and per-PID response extraction
- **LIN tap:** RJ45 pin 3 wired directly to logic analyzer / ESP32 GPIO16 (RX only)
- **Sessions:** Multiple captures at different desk states (idle, moving up, moving down, preset recall)

Raw `.sr` capture files are no longer available.

## Why LIN injection failed

The LIN bus uses an open-collector physical layer. Every transmitter on the bus can pull the line LOW but not drive it HIGH (the bus pull-up resistor does that). The bus state is the bitwise AND of all transmitters' outputs.

When the panel sends `0x05` (idle) and the ESP simultaneously sends `0x0A` (UP):

```
Panel output:  0x05  =  0000 0101
ESP output:    0x0A  =  0000 1010
Bus result:    AND   =  0000 0000  =  0x00
```

The master sees `0x00` — a corrupt frame. It rejects it, and the panel's LED blinks (bus error detected).

**This is not a timing or implementation problem. It's a fundamental physical constraint.** You cannot override another active transmitter on an open-collector bus. The only way to inject is to physically disconnect the panel from the bus during the injection window.

## What would unlock full LIN control

1. **Hardware switch** (MOSFET or analog mux) to disconnect panel TX from the bus during ESP injection windows
2. **Full PID response coverage** — ESP must respond to all ~8 PIDs that currently get panel responses (we only decoded ~4)
3. **Correct iDrive checksum** for PID 0x92 — without this, the controller rejects injected movement commands
4. **Timing precision** — responses must arrive within the controller's timeout window after each PID poll

This is achievable but requires significantly more hardware and reverse engineering effort than the button emulation approach.
