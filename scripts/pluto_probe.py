#!/usr/bin/env python3
"""Probe one or more PlutoSDRs and print the core radio settings.

Example:
  python scripts/pluto_probe.py --uri ip:192.168.8.93 --uri ip:192.168.8.94
"""
import argparse
import json
import sys

import adi


def read_attr(obj, name):
    try:
        return getattr(obj, name)
    except Exception as exc:  # hardware attrs can fail if context is stale
        return f"<error: {exc}>"


def probe(uri: str) -> dict:
    sdr = adi.Pluto(uri=uri)
    fields = [
        "uri",
        "sample_rate",
        "rx_rf_bandwidth",
        "tx_rf_bandwidth",
        "rx_lo",
        "tx_lo",
        "rx_hardwaregain_chan0",
        "tx_hardwaregain_chan0",
        "gain_control_mode_chan0",
        "rx_buffer_size",
        "tx_cyclic_buffer",
    ]
    result = {"uri": uri}
    for field in fields[1:]:
        result[field] = read_attr(sdr, field)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe PlutoSDR connection/settings")
    parser.add_argument("--uri", action="append", required=True, help="Pluto URI, e.g. ip:192.168.2.1 or usb:")
    args = parser.parse_args()

    ok = True
    for uri in args.uri:
        try:
            print(json.dumps(probe(uri), indent=2, default=str))
        except Exception as exc:
            ok = False
            print(f"ERROR probing {uri}: {exc}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
