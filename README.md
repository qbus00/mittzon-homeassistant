# Mittzon Standing Desk → Home Assistant via ESPHome

Control an IKEA Mittzon standing desk from Home Assistant using an ESP32 wired directly to the handset panel's button contacts.

## What works

- **UP / DOWN** control from Home Assistant switches
- **Memory preset** buttons (M1, M2) via HA button entities
- **Live height tracking** (cm + raw encoder ticks) via LIN bus RX monitoring
- **Movement state** sensor (idle / up / down)
- **End-stop protection** — soft limits prevent driving past safe range
- **Physical button safety** — if someone presses DOWN past the limit on the panel, ESP fires UP to trigger the controller's "two buttons = STOP" behavior
- **Deadman timer** — 30s max hold, auto-release

## What doesn't work (yet)

- Full LIN bus control (iDrive proprietary checksum not cracked — see [PROTOCOL.md](PROTOCOL.md))
- Go-to-position automation (would need LIN injection or timed drive with position feedback)
- Panel LED status reading

## Quick start

1. Open your Mittzon handset panel and solder 4 wires to the button pads (UP, DOWN, M1, M2) + GND
2. Connect to ESP32 GPIOs in open-drain mode (see [HARDWARE.md](HARDWARE.md))
3. Tap LIN bus (RJ45 pin 3) directly to GPIO16
4. Copy `esphome/qbus-desk.yaml` to your ESPHome config directory
5. Create a `secrets.yaml` with your WiFi credentials, API key, and OTA password
6. Flash and add to Home Assistant

See [HARDWARE.md](HARDWARE.md) for full wiring details and panel teardown instructions.

## Hardware

- ESP32 WROOM-32 DevKit
- Thin silicone wires (AWG28-30)
- Powered directly from ROL desk controller 5V rail

Total cost beyond the desk: ~$3 if you have an ESP32 lying around.

## Wiring overview

```
[ROL Group Controller]
       |
       | RJ45 cable (LIN bus + power)
       |
[Mittzon Handset Panel]
   |   |   |   |   |
  UP  DOWN M1  M2  GND
   |   |   |   |   |
   |   |   |   |   +-----+
   |   |   |   |         |
   |   |   |   +---+     |
   |   |   |       |     |
   |   |   +---+   |     |
   |   |       |   |     |
   |   +---+   |   |     |
   |       |   |   |     |
[GPIO26] [27] [33] [32] [GND]   <-- ESP32 WROOM-32
                                    (open-drain mode)

LIN bus tap (separate connection):
RJ45 pin 3 ----------- GPIO16 (UART2 RX)
RJ45 pin 8 ----------- ESP GND (shared with panel GND)

Power (from ROL desk controller):
RJ45 5V   ------------ ESP32 VIN (5V)
RJ45 GND  ------------ ESP32 GND
```

## Home Assistant entities

| Entity | Type | Description |
|---|---|---|
| Desk Up | Switch | Hold to raise, release to stop |
| Desk Down | Switch | Hold to lower, release to stop |
| Desk M1 | Button | Momentary press for memory 1 |
| Desk M2 | Button | Momentary press for memory 2 |
| Desk Height | Sensor | Current height in cm |
| Desk Position | Sensor | Raw encoder ticks |
| Desk Movement | Text Sensor | idle / up / down |
| Desk At Top | Binary Sensor | At upper end-stop |
| Desk At Soft Bottom | Binary Sensor | At lower soft limit |

## The journey

This wasn't the first approach. The full story — including LIN bus reverse engineering, a hardware MITM bridge, and why injection on an open-collector bus is mathematically impossible — is in [JOURNEY.md](JOURNEY.md).

The protocol findings (decoded PIDs, frame formats, what remains unsolved) are in [PROTOCOL.md](PROTOCOL.md).

## Project structure

```
├── README.md          # This file
├── HARDWARE.md        # Wiring, components, panel teardown
├── PROTOCOL.md        # iDrive/LIN bus findings
├── JOURNEY.md         # Full story including failed attempts
├── esphome/
│   └── qbus-desk.yaml # Final working ESPHome config
├── scripts/
│   ├── sigrok-decode.py # LIN frame decoder for sigrok captures
│   └── lin-analyze.py   # Per-second PID rate analysis
└── LICENSE            # MIT
```

## Suggested topics

`homeassistant` `esphome` `esp32` `ikea-mittzon` `standing-desk` `lin-bus` `reverse-engineering` `smart-home` `home-automation`

## License

MIT
