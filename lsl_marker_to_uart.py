# -*- coding: utf-8 -*-
"""接收 patient.py 发送的 LSL marker / VAS-D 分值，并转发到 UART。"""

import argparse
import os
import sys
import time
import tomllib

from pylsl import StreamInlet, resolve_byprop
import serial
from serial import SerialException


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "lsl_markers.toml")
UART_HEADER = 0x36


def load_lsl_config(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def resolve_marker_stream(stream_cfg, timeout):
    source_id = str(stream_cfg.get("source_id", "")).strip()
    name = str(stream_cfg.get("name", "")).strip()
    stream_type = str(stream_cfg.get("type", "")).strip()

    lookups = []
    if source_id:
        lookups.append(("source_id", source_id))
    if name:
        lookups.append(("name", name))
    if stream_type:
        lookups.append(("type", stream_type))

    for prop, value in lookups:
        streams = resolve_byprop(prop, value, minimum=1, timeout=timeout)
        if streams:
            return streams[0], prop, value
    return None, None, None


def marker_label(sample_value, markers):
    for name, value in markers.items():
        if int(value) == sample_value:
            return name
    if 0 <= sample_value <= 10:
        return "VAS-D score"
    return "unknown"


def marker_byte(sample_value):
    value = int(sample_value)
    if not 0 <= value <= 255:
        raise ValueError(f"LSL sample value {value} is outside UART byte range 0-255")
    return value


def open_uart(uart_cfg):
    port = str(uart_cfg.get("port", "")).strip()
    if not port:
        raise ValueError("UART port 未配置，请在 lsl_markers.toml 的 [uart].port 中设置")

    if "baudrate" not in uart_cfg:
        raise ValueError("UART baudrate 未配置，请在 lsl_markers.toml 的 [uart].baudrate 中设置")
    baudrate = int(uart_cfg["baudrate"])
    timeout = float(uart_cfg.get("timeout_s", 1.0))
    write_timeout = float(uart_cfg.get("write_timeout_s", 1.0))
    uart = serial.serial_for_url(
        port,
        baudrate=baudrate,
        timeout=timeout,
        write_timeout=write_timeout,
    )
    print(
        f"UART connected: port={port}, baudrate={baudrate}, "
        f"timeout={timeout}, write_timeout={write_timeout}",
        flush=True,
    )
    return uart


def send_uart_marker(uart, value):
    data = marker_byte(value)
    payload = bytes([UART_HEADER, data])
    written = uart.write(payload)
    uart.flush()
    if written != len(payload):
        raise IOError(f"UART write incomplete: wrote {written}/{len(payload)} bytes")
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Receive LSL int8 markers and forward them to UART as [0x36, data].",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="Path to lsl_markers.toml.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Seconds to wait during each stream discovery attempt.",
    )
    args = parser.parse_args()

    cfg = load_lsl_config(args.config)
    stream_cfg = cfg["stream"]
    markers = dict(cfg.get("markers", {}))
    uart_cfg = dict(cfg.get("uart", {}))

    try:
        with open_uart(uart_cfg) as uart:
            print(
                "Resolving LSL stream: "
                f"name={stream_cfg.get('name')}, "
                f"type={stream_cfg.get('type')}, "
                f"source_id={stream_cfg.get('source_id')}",
                flush=True,
            )

            stream = None
            while stream is None:
                stream, prop, value = resolve_marker_stream(stream_cfg, args.timeout)
                if stream is None:
                    print("No stream found, retrying...", flush=True)
                    time.sleep(1.0)

            print(f"Connected by {prop}={value}", flush=True)
            print(
                "Stream info: "
                f"name={stream.name()}, type={stream.type()}, "
                f"source_id={stream.source_id()}, "
                f"channel_format={stream.channel_format()}",
                flush=True,
            )

            inlet = StreamInlet(stream)
            print("Receiving samples. Press Ctrl+C to stop.", flush=True)
            print("Print format: timestamp\tvalue\tlabel\tuart_payload", flush=True)
            while True:
                sample, timestamp = inlet.pull_sample(timeout=1.0)
                if sample is None:
                    continue
                value = marker_byte(sample[0])
                label = marker_label(value, markers)
                payload = send_uart_marker(uart, value)
                print(
                    f"{timestamp:.6f}\t{value}\t{label}\t{payload.hex(' ')}",
                    flush=True,
                )
                if label == "paradigm_end":
                    print("Received paradigm_end. Stopped.", flush=True)
                    return 0
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        return 0
    except (OSError, SerialException, ValueError) as err:
        print(f"UART setup failed: {err}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
