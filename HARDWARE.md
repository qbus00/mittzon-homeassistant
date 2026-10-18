# Hardware

## Components

| Part | Quantity | Notes |
|---|---|---|
| ESP32 WROOM-32 DevKit | 1 | Any common dev board works |
| Thin silicone wire (AWG28-30) | ~30cm | For button pad taps |

No optocouplers, no level shifters, no resistors, no separate power supply. The ESP32 is powered directly from the ROL desk controller's 5V rail.

## Wiring

### Button connections

| Panel button pad | ESP32 GPIO | Mode |
|---|---|---|
| UP | GPIO26 | Output, open-drain |
| DOWN | GPIO27 | Output, open-drain |
| M1 | GPIO33 | Output, open-drain |
| M2 | GPIO32 | Output, open-drain |
| GND (shared) | GND | Common ground |

### LIN bus tap

| Source | Destination | Notes |
|---|---|---|
| RJ45 pin 3 (LIN bus) | GPIO16 (UART2 RX) | Direct connection |
| RJ45 pin 8 (GND) | ESP32 GND | Shared ground |

### Power

| Source | Destination | Notes |
|---|---|---|
| ROL desk controller 5V | ESP32 VIN | Powers the ESP32 directly |
| ROL desk controller GND | ESP32 GND | Shared with panel GND |

### Full wiring diagram

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
5V  ------------------- ESP32 VIN
GND ------------------- ESP32 GND
```

## Panel teardown

1. The Mittzon handset panel clips off the desk frame. Remove it and undo the screws on the back.
2. Inside is a small PCB with 4 momentary tactile buttons.
3. Each button has a signal pad and shares a common ground.

### Button pad electrical characteristics

- Signal pads idle at 3.3V (pulled up from the panel's MCU)
- Pressing a button shorts the signal pad to GND
- This is exactly what our ESP32 GPIO replicates in open-drain mode

### Test points on the handset PCB

Instead of cutting the original RJ45 cable, everything can be tapped at test points on the handset PCB (measured on a real panel):

| Test point | Signal | ESP32 |
|---|---|---|
| TP5 | M1 button pad | GPIO33 |
| TP6 | UP button pad | GPIO26 |
| TP7 | DOWN button pad | GPIO27 |
| TP8 | M2 button pad | GPIO32 |
| TP10 | 5V | VIN |
| TP12 | LIN bus | GPIO16 (UART2 RX) |
| any GND point | GND | GND |

Verify the pads with a multimeter before soldering: the button pads idle at 3.3V and the LIN line idles near the supply voltage.

### Soldering the taps

Solder one thin wire to each of the 4 button signal pads (UP, DOWN, M1, M2) and one to any GND point on the PCB. Route the wires out through the cable channel.

## Why direct GPIO works (no optocoupler needed)

1. **Voltage match** — Panel buttons operate at 3.3V, same as ESP32 GPIO
2. **Common ground** — ESP32 and panel share GND, so voltage references are aligned
3. **Open-drain mode** — GPIO configured as open-drain can only pull LOW (assert) or float (release). It never drives HIGH, so there's no risk of back-current into the panel's pull-up resistors
4. **Galvanic isolation unnecessary** — Both devices are grounded together intentionally. The desk controller's power rail is separate from the button signals

This saves 4 optocouplers and simplifies the build significantly.

## LIN bus tap

The LIN bus runs on RJ45 pin 3 between the controller and handset panel. We tap it **receive-only** directly to ESP32 GPIO16 (hardware UART2 RX). Since we're only receiving (not transmitting), there's no risk of bus disruption from this tap.

### RJ45 pinout (observed)

| Pin | Function |
|---|---|
| 3 | LIN bus (data) |
| 8 | GND |
| Others | Power rails (not tapped) |

## Caveats

- **Parallel wiring** — Physical buttons remain fully functional. The ESP32 GPIO taps are wired in parallel with the panel's own buttons.
- **Assert-only** — ESP can drive a button LOW (pressed) but cannot force it HIGH if the user is physically holding the button down.
- **Safety via "two buttons = STOP"** — The ROL Group controller has built-in behavior: if two buttons are active simultaneously, it stops all motion. The firmware exploits this for physical button safety (see [JOURNEY.md](JOURNEY.md#5-final-safety-features)).
