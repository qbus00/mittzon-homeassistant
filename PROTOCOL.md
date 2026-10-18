# LIN Bus Protocol Findings

Reverse engineering notes for the LIN protocol used between the IKEA Mittzon standing desk's ROL Group controller and handset panel.

> **2026 update:** An ESPHome-based re-capture (the "Desk LIN Capture" toggle in `esphome/qbus-desk.yaml`) corrected two earlier mistakes:
> 1. Desk **position lives in the first two payload bytes**, not bytes 2–3 as the original notes claimed.
> 2. The checksum is **standard LIN enhanced** — there is no proprietary "iDrive" algorithm. The proprietary-checksum conclusion was an artifact of misframing the payload. All 734 payload-bearing frames in the re-capture verify against LIN enhanced.

## Bus characteristics

- **Baud rate:** 19200
- **Format:** 8N1
- **Physical layer:** Single-wire LIN-like bus on RJ45 pin 3
- **Topology:** Controller is master (polls every PID); panel answers a subset
- **Frame structure:** BREAK + SYNC (0x55) + PID + data bytes + checksum

## PID schedule

The master (controller) continuously polls 12 PIDs in a cyclic schedule. In an idle/steady capture only four carry a data response; the rest are polled but return no payload — either no slave answers, or the slave only answers when it has something to report (e.g. a button press).

| PID | Approx. rate | Response in idle/steady capture |
|---|---|---|
| 0x03 | ~10/s | none |
| 0x06 | ~10/s | none |
| 0x08 | ~10/s | position + flag |
| 0x11 | ~10/s | constant |
| 0x42 | ~10/s | none |
| 0x47 | ~10/s | none |
| 0x50 | **~70/s** | none (keepalive header) |
| 0x80 | ~10/s | constant |
| 0x85 | ~10/s | none |
| 0x92 | ~10/s | position + status |
| 0xC1 | ~10/s | none |
| 0xC4 | ~10/s | none |

Total bus utilization: ~190 frames/second.

The seven "none" PIDs are the prime suspects for carrying the panel's button/preset commands — they were empty only because no button was pressed while they happened to be polled. Confirming this needs targeted single-action captures (hold UP only, hold DOWN only, recall M1, recall M2).

## Frame layouts

Every multi-byte frame ends with a LIN enhanced checksum (see below). Position is a little-endian uint16 in the **first two payload bytes**.

### PID 0x92 — position + status

```
posL posH status CHK
```

- **posL posH:** position, little-endian uint16, encoder ticks
- **status:** a state/phase byte. Observed values and counts in one up-then-down capture:

| Status | Count | Context (tentative) |
|---|---|---|
| 0x44 | 79 | steady / at rest |
| 0x06 | 53 | — |
| 0x05 | 43 | — |
| 0x07 | 6 | around motion |
| 0x04 | 2 | around motion |

The same status values appear while moving **both** up and down, so this byte looks like a motion/phase status **reported by the controller**, not a directional button command. (Position is something only the controller's encoder knows, which reinforces that 0x92 is controller→panel status.) Exact semantics are not yet confirmed.

### PID 0x08 — position + flag

```
posL posH flag CHK
```

- **posL posH:** position, little-endian uint16, encoder ticks (same value as 0x92 in the same poll cycle)
- **flag:** 0x00 or 0x02 (purpose unconfirmed)

Position range in the sample capture: 1668–3279 ticks (76.5–92.1 cm). Calibration: 102.93 ticks/cm, zero offset 60.29 cm. Full physical range is ~888–6669 ticks.

### PID 0x11 — constant

`00 00 00 CHK` → `00 00 00 EE`

### PID 0x80 — constant

`00 00 00 00 00 00 00 00 CHK` → `… 7F`

## Error / calibration state (desk shows orange)

Observed on a desk that dropped into the "calibrate me" state. All frames still pass the LIN enhanced checksum, so the bus itself is healthy.

| PID | Payload | Meaning (tentative) |
|---|---|---|
| 0x92 | `00 FF 44` | position **0xFF00** = no reference, status 0x44 |
| 0x08 | `00 FF 00` | position 0xFF00, flag 0x00 |

While the handset was being recalibrated the following was logged (via `Desk LIN Capture` plus the change-only `lin` log):

- 0x92 `00 00 05` and 0x08 flag `0x04` appear mixed into the 0xFF00 frames: position 0, status 0x05, while a button is pressed.
- 0x08 then reports rising positions (`0x0048` … `0x008D`, flag 0x00) while the desk drives, then 0x92 status 0x04 (moving) at `0x0063` … `0x008D`, and finally the normal rest status 0x44 at `0x008D`.
- Flags seen on 0x08: 0x00, 0x01, 0x02, 0x04. Statuses seen on 0x92: 0x04, 0x05, 0x06, 0x44.

Position 0x0000 and 0xFF00 are therefore not real heights; the firmware treats both as "do not touch the buttons". The earlier firmware silently dropped 0xFF00 frames (`pos > 20000`) and, on position 0, its below-minimum auto-recovery held UP, which fights a manual recalibration on the handset (two buttons = stop).

## Checksum — standard LIN enhanced

The checksum is the **LIN enhanced checksum**: the inverted, carry-folded 8-bit sum of the **protected ID (PID) plus all data bytes**.

```
sum = PID + data[0] + data[1] + ...
while sum > 0xFF:
    sum = (sum & 0xFF) + (sum >> 8)   # carry fold
checksum = (~sum) & 0xFF
```

Worked examples from the capture:

- PID `0x08`, data `84 06 00`, chk `6D`: `0x08 + 0x84 + 0x06 + 0x00 = 0x92`, `~0x92 = 0x6D` ✓
- PID `0x92`, data `84 06 44`, chk `9E`: `0x92 + 0x84 + 0x06 + 0x44 = 0x160` → fold → `0x61` → `~0x61 = 0x9E` ✓

Verified across the entire ESPHome capture:

| PID | Frames matching LIN enhanced |
|---|---|
| 0x08 | 184 / 184 |
| 0x11 | 184 / 184 |
| 0x80 | 183 / 183 |
| 0x92 | 183 / 183 |
| **Total** | **734 / 734** |

### Why the original analysis thought it was proprietary

The earlier sigrok-based notes read position from the wrong byte offset and treated the leftover bytes as the payload, so the byte set fed into the checksum was wrong — and naturally never matched LIN classic or enhanced. That produced the "proprietary iDrive checksum" conclusion. There is no proprietary checksum; it is textbook LIN enhanced.

## Capture methodology

Two capture paths have been used:

- **ESPHome (current):** `esphome/qbus-desk.yaml` has a "Desk LIN Capture" toggle that hex-dumps every frame (log tag `LINCAP`) over the network log stream. Continuous, byte-aligned, and trivial to reproduce for every desk state. Decode with `scripts/sigrok-decode.py`, which auto-detects a LINCAP log.
- **sigrok (original):** sigrok-cli with a 24MHz/4MHz USB logic analyzer on Mac M1, tapping RJ45 pin 3. Raw `.sr` files from those sessions are no longer available.

## Why LIN injection still isn't trivial

Cracking the checksum removes the *encoding* blocker, not the *physical* one. The LIN bus is open-collector: every transmitter can pull the line LOW but not drive it HIGH, so the bus is the bitwise AND of all transmitters. You cannot override the panel's response by adding a second transmitter — the panel's zeros win.

```
Panel:  0x05 = 0000 0101
ESP:    0x0A = 0000 1010
Bus:    AND  = 0000 0000   ← corrupt frame
```

So native control still requires **removing the panel from the response slot**, one of:

1. **Replace the panel** — unplug it; ESP + a LIN transceiver answers every PID the controller expects. Needs the full set of panel-sourced PIDs and their data (the checksum is now known).
2. **Mute the panel's TX** — a MOSFET/analog switch that disconnects the panel during the specific response slot the ESP wants to own, with tight timing.

## Open questions

1. **Which PID carries the button/preset command?** Likely one of the currently-empty PIDs; needs targeted UP-only / DOWN-only / M1 / M2 captures.
2. **Source direction per PID** — controller-sourced vs panel-sourced. A capture with the panel unplugged (ESP still RX-tapped) settles this: PIDs still answered are controller-sourced; those that go silent are panel-sourced.
3. **0x92 status-byte semantics** and the **0x08 flag byte**.
4. Whether presets (M1/M2) issue a bus-visible "go to height" command — the path to the controller's native ~0.1 cm precision.
