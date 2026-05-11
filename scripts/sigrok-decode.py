#!/usr/bin/env python3
"""LIN frame decoder for sigrok captures of the Mittzon iDrive bus.

Reads raw bytes from stdin (e.g., piped from sigrok-cli) and extracts
LIN frames: BREAK + SYNC (0x55) + PID + response bytes.

Usage:
    sigrok-cli -i capture.sr -P uart:baudrate=19200:rx=D0 -B uart | python3 sigrok-decode.py
    cat raw_bytes.bin | python3 sigrok-decode.py
"""

import sys
import struct
from collections import defaultdict


SYNC_BYTE = 0x55

KNOWN_PIDS = {
    0x03: "unknown",
    0x06: "unknown",
    0x08: "position",
    0x11: "constant",
    0x42: "unknown",
    0x47: "unknown",
    0x50: "keepalive",
    0x80: "constant",
    0x85: "unknown",
    0x92: "movement_state",
    0xC1: "unknown",
    0xC4: "unknown",
}


def lin_checksum_enhanced(pid: int, data: bytes) -> int:
    """LIN enhanced checksum: sum of PID + all data bytes, carry-folded, inverted."""
    s = pid
    for b in data:
        s += b
        if s > 0xFF:
            s -= 0xFF
    return (~s) & 0xFF


def lin_checksum_classic(data: bytes) -> int:
    """LIN classic checksum: sum of data bytes only, carry-folded, inverted."""
    s = 0
    for b in data:
        s += b
        if s > 0xFF:
            s -= 0xFF
    return (~s) & 0xFF


def decode_pid_0x92(data: bytes) -> str:
    if not data:
        return "empty"
    state = data[0]
    states = {0x05: "idle", 0x0A: "UP", 0x44: "settling", 0x00: "transition"}
    return states.get(state, f"unknown(0x{state:02X})")


def decode_pid_0x08(data: bytes) -> str:
    if len(data) >= 4:
        pos = struct.unpack_from("<H", data, 2)[0]
        return f"position={pos} ticks"
    return f"{len(data)} bytes"


def decode_frame(pid: int, data: bytes) -> str:
    hex_data = " ".join(f"0x{b:02X}" for b in data)
    label = KNOWN_PIDS.get(pid, "unknown")

    detail = ""
    if pid == 0x92:
        detail = f" [{decode_pid_0x92(data)}]"
    elif pid == 0x08:
        detail = f" [{decode_pid_0x08(data)}]"

    chk_e = lin_checksum_enhanced(pid, data[:-1]) if len(data) > 1 else None
    chk_c = lin_checksum_classic(data[:-1]) if len(data) > 1 else None
    actual_chk = data[-1] if data else None

    chk_info = ""
    if actual_chk is not None and len(data) > 1:
        if actual_chk == chk_e:
            chk_info = " checksum=enhanced_OK"
        elif actual_chk == chk_c:
            chk_info = " checksum=classic_OK"
        else:
            chk_info = f" checksum=MISMATCH(got=0x{actual_chk:02X} enhanced=0x{chk_e:02X} classic=0x{chk_c:02X})"

    return f"PID 0x{pid:02X} ({label}): {hex_data}{detail}{chk_info}"


def main():
    data = sys.stdin.buffer.read()
    if not data:
        print("No input data. Pipe raw UART bytes to stdin.", file=sys.stderr)
        sys.exit(1)

    frame_count = defaultdict(int)
    i = 0
    while i < len(data) - 1:
        if data[i] == SYNC_BYTE and data[i + 1] in KNOWN_PIDS:
            pid = data[i + 1]
            # Collect response bytes until next SYNC or end of data
            resp_start = i + 2
            resp_end = resp_start
            while resp_end < len(data) - 1:
                if data[resp_end] == SYNC_BYTE and data[resp_end + 1] in KNOWN_PIDS:
                    break
                resp_end += 1
            if resp_end >= len(data) - 1:
                resp_end = len(data)

            resp = data[resp_start:resp_end]
            frame_count[pid] += 1
            print(decode_frame(pid, resp))
            i = resp_end
        else:
            i += 1

    print(f"\n--- Summary ---")
    print(f"Total frames decoded: {sum(frame_count.values())}")
    for pid in sorted(frame_count):
        label = KNOWN_PIDS.get(pid, "unknown")
        print(f"  PID 0x{pid:02X} ({label}): {frame_count[pid]} frames")


if __name__ == "__main__":
    main()
