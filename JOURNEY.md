# The Journey

How an IKEA Mittzon standing desk ended up in Home Assistant — including every wrong turn.

## The goal

Control a Mittzon standing desk from Home Assistant. Raise it, lower it, recall presets, read the current height. Simple enough in theory.

The Mittzon uses a ROL Group controller with a proprietary protocol called iDrive, running over what looks like a LIN bus on an RJ45 cable between the controller and the handset panel. There's no official API, no Bluetooth, no documented protocol.

## Attempt 1: Full LIN protocol reverse engineering

The first idea was the "correct" one — decode the protocol, speak it natively, and control the desk as a proper bus participant.

### Setting up the capture

Tapped RJ45 pin 3 (the data line) with a logic analyzer running at 24MHz, later 4MHz. Used sigrok-cli on a Mac M1 for capture and a custom Python decoder for frame parsing.

The bus speaks 19200 baud, 8N1 — standard LIN framing with BREAK, SYNC byte (0x55), and PID.

### What we found

The master polls 12 PIDs in a cyclic schedule at ~190 frames/second total. PID 0x50 dominates at ~70/s (keepalive filler). The interesting PIDs are 0x08 (position data) and 0x92 (movement state from the panel).

We decoded response formats for about 4 PIDs. The position data lives in PID 0x08 as a little-endian uint16 in encoder ticks. PID 0x92 carries the panel's button state — `0x05` for idle, `0x0A` for UP.

Full findings are in [PROTOCOL.md](PROTOCOL.md).

### Where it stalled

The iDrive protocol uses a proprietary checksum on at least some PIDs. Standard LIN classic and enhanced checksums match for PIDs 0x80 and 0x11, but not for 0x92 — the PID we'd need to inject movement commands.

Without the checksum, we can't construct valid frames. We tried XOR variants, CRC-8 polynomials, and sum-with-seed approaches. Nothing matched.

## Attempt 2: Hardware MITM bridge

If we can't crack the checksum, maybe we don't need to. The plan: sit between the controller and panel, forward everything transparently, but swap out PID 0x92 responses when we want to inject commands.

### The build

Cut RJ45 pin 3 between controller (A-side) and panel (F-side). Two BC547 transistors for bus separation. ESP32 in the middle monitoring both sides.

```
Controller ←→ [ESP32 MITM bridge] ←→ Panel
              A-side    F-side
```

The ESP monitors both sides and forwards BREAK signals via GPIO bit-banging (hardware UART BREAK didn't work due to FIFO requirements — the UART peripheral needs specific framing that doesn't map to raw BREAK timing).

### What worked

Monitoring was perfect. The ESP could see every frame on both sides of the cut, decode PIDs, and log traffic in real time.

### What didn't work

Injection. And this is where it gets interesting.

## Attempt 3: Understanding why injection is impossible

The LIN bus uses an open-collector physical layer. This means:

- Every transmitter can pull the bus LOW (assert a zero bit)
- No transmitter can drive the bus HIGH (the pull-up resistor does that)
- The bus state is the **bitwise AND** of all connected transmitters

When the panel sends its idle response (`0x05` = `0000 0101`) and the ESP simultaneously tries to inject UP (`0x0A` = `0000 1010`):

```
Panel:  0000 0101  (0x05)
ESP:    0000 1010  (0x0A)
Bus:    0000 0000  (0x00)  ← AND result
```

The master sees `0x00` — garbage. Frame rejected. Panel LED blinks to signal a bus error.

**This isn't a timing problem or a firmware bug. It's physics.** On an open-collector bus, you can only add zeros to what's already there. You can never override another transmitter's zeros with your ones.

Even in the MITM configuration, the panel is still connected to its side of the bus and actively responding. We'd need to electrically disconnect the panel's transmitter during injection — a MOSFET switch on the panel TX line, triggered with microsecond precision in the gap between the master's PID poll and the panel's response.

Plus, the ESP would need to respond correctly to all PIDs the panel currently handles (we only decoded ~4 of ~8 needed), with the correct iDrive checksum that we haven't cracked.

This approach is theoretically possible but requires significantly more hardware and reverse engineering. We pivoted.

## Attempt 4: Direct button emulation

Sometimes the best hack is the simplest one.

### Opening the panel

The Mittzon handset panel pops off the desk frame. Inside: a small PCB with 4 momentary tactile buttons (UP, DOWN, M1, M2) sharing a common ground. Each button pad idles at 3.3V (pulled up from the panel's MCU) and goes to GND when pressed.

### The realization

This is just 4 switches to ground. An ESP32 GPIO in open-drain mode does exactly the same thing — it can pull to GND (assert) or float (release). No optocoupler needed because:

- Panel buttons are 3.3V — same as ESP32 GPIO levels
- Common ground is shared
- Open-drain mode never drives HIGH, so no back-current into pull-ups

Four wires soldered to button pads, one to GND, and the ESP32 can "press" any button.

### Adding position feedback

The LIN bus tap from the earlier attempts was already wired up. Even though we can't inject on the bus, we can still listen. PID 0x92 carries movement state and PID 0x08 carries position data. ESPHome's UART debug component parses frames in a lambda, extracting position ticks and converting to centimeters.

This gives us closed-loop control: the ESP presses UP, monitors position via LIN, and releases when it reaches the target (or a safety limit).

## Attempt 5: Making it safe

A desk that moves under remote control needs to not crush things.

### End-stop protection

The desk's physical range maps to encoder ticks ~888 (lowest) to ~6669 (highest). The firmware enforces soft limits:

- **On switch turn_on:** If position is already at or past the limit, the switch refuses to engage
- **During motion:** Lambda in the UART handler checks position every frame (~10/s) and kills the switch if the limit is reached

### Deadman timer

Every switch action has a 30-second maximum hold. If Home Assistant crashes, loses WiFi, or the automation hangs, the button releases after 30 seconds. The desk controller also has its own internal timeout, so this is defense-in-depth.

### Physical button safety

Here's the tricky one: what if someone presses the physical DOWN button on the panel and drives the desk past our soft bottom limit?

The ESP can't prevent this — it can only add button presses, not block them (open-drain, remember). But the ROL Group controller has a built-in safety behavior: **if two buttons are active simultaneously, it stops all motion**.

So the firmware monitors for descent past the bottom limit via LIN position data. If detected while the HA DOWN switch is off (meaning someone is using the physical button), it fires the UP GPIO for 500ms. The controller sees two buttons and stops. The physical user gets a brief unexpected stop, which is better than the desk hitting something.

## The result

The desk is fully controllable from Home Assistant with live height tracking, safety limits, and physical button override protection. The ESPHome config is straightforward — no custom components, just YAML with lambdas.

Total hardware cost beyond the desk: an ESP32 and some wire. Powered directly from the desk's 5V rail.

## Lessons learned

1. **Understand the physical layer before writing code.** The open-collector AND behavior made injection impossible, and we didn't realize it until after building the MITM hardware. A few minutes with the LIN spec would have saved hours.

2. **Proprietary protocols on commodity hardware often have a simpler bypass.** The iDrive protocol is sophisticated, but the buttons are just switches to ground.

3. **Failed approaches aren't wasted.** The LIN monitoring from the injection attempts became the position feedback system. The bus analysis informed the safety limits.

4. **"Two buttons = stop" is a feature, not a bug.** A safety behavior in the controller became our physical override mechanism.

