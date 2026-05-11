#!/usr/bin/env python3
"""Per-second PID rate analysis for Mittzon iDrive LIN bus captures.

Reads raw UART bytes from stdin, groups LIN frames into 1-second windows
based on byte position (assuming continuous capture at 19200 baud), and
prints per-second PID counts.

Usage:
    sigrok-cli -i capture.sr -P uart:baudrate=19200:rx=D0 -B uart | python3 lin-analyze.py
"""

import sys
from collections import defaultdict

SYNC_BYTE = 0x55
BAUD_RATE = 19200
BITS_PER_BYTE = 10  # 8N1 = start + 8 data + stop
BYTES_PER_SECOND = BAUD_RATE / BITS_PER_BYTE

KNOWN_PIDS = {
    0x03: "unknown_03",
    0x06: "unknown_06",
    0x08: "position",
    0x11: "constant_11",
    0x42: "unknown_42",
    0x47: "unknown_47",
    0x50: "keepalive",
    0x80: "constant_80",
    0x85: "unknown_85",
    0x92: "movement",
    0xC1: "unknown_C1",
    0xC4: "unknown_C4",
}


def main():
    data = sys.stdin.buffer.read()
    if not data:
        print("No input data. Pipe raw UART bytes to stdin.", file=sys.stderr)
        sys.exit(1)

    # Collect (byte_offset, pid) for each detected frame
    frames = []
    i = 0
    while i < len(data) - 1:
        if data[i] == SYNC_BYTE and data[i + 1] in KNOWN_PIDS:
            frames.append((i, data[i + 1]))
            i += 2
        else:
            i += 1

    if not frames:
        print("No LIN frames found in input.", file=sys.stderr)
        sys.exit(1)

    # Group into 1-second windows by byte offset
    window_size = int(BYTES_PER_SECOND)
    max_offset = frames[-1][0]
    num_windows = (max_offset // window_size) + 1

    print(f"Capture length: ~{num_windows} seconds ({len(data)} bytes)")
    print(f"Total frames: {len(frames)}")
    print()

    # Header
    all_pids = sorted(set(pid for _, pid in frames))
    header = f"{'Second':>6}"
    for pid in all_pids:
        header += f"  0x{pid:02X}"
    header += "  TOTAL"
    print(header)
    print("-" * len(header))

    for window in range(num_windows):
        start = window * window_size
        end = start + window_size
        counts = defaultdict(int)
        for offset, pid in frames:
            if start <= offset < end:
                counts[pid] += 1

        if not counts:
            continue

        row = f"{window:>6}"
        total = 0
        for pid in all_pids:
            c = counts.get(pid, 0)
            total += c
            row += f"  {c:>4}"
        row += f"  {total:>5}"
        print(row)

    # Summary: average rates
    total_seconds = max(1, num_windows)
    print()
    print("--- Average rates (frames/sec) ---")
    pid_totals = defaultdict(int)
    for _, pid in frames:
        pid_totals[pid] += 1
    for pid in sorted(pid_totals):
        label = KNOWN_PIDS.get(pid, "unknown")
        rate = pid_totals[pid] / total_seconds
        print(f"  PID 0x{pid:02X} ({label:>12}): {rate:6.1f}/s  ({pid_totals[pid]} total)")
    print(f"  {'TOTAL':>26}: {len(frames) / total_seconds:6.1f}/s  ({len(frames)} total)")


if __name__ == "__main__":
    main()
