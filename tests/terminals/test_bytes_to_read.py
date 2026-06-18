"""Regression test for pyinvoke/invoke#1070: bytes_to_read on Python 3.14

On Python 3.14, fcntl.ioctl rejects undersized mutable buffers
(cpython#144206). bytes_to_read passed a 2-byte buffer to FIONREAD, which
writes a C int (4 bytes). Worked by accident on <=3.13 due to a 1024-byte
static copy buffer that masked the size mismatch.

The fix matches the buffer size to the C int (4 bytes) and updates the
struct format from 'h' (signed short, 2 bytes) to 'i' (signed int, 4 bytes).
"""

import struct
from unittest import mock

import pytest

from invoke.terminals import bytes_to_read


def test_bytes_to_read_uses_4byte_buffer(monkeypatch):
    """fcntl.ioctl must be called with a 4-byte buffer for FIONREAD, not 2."""
    captured = {}

    def fake_ioctl(fd, request, buf, *args, **kwargs):
        captured["buf"] = buf
        captured["len"] = len(buf) if hasattr(buf, "__len__") else None
        # Return a 4-byte buffer that decodes to a sensible int when parsed
        # as 'i' (4-byte signed int)
        return struct.pack("i", 42)

    monkeypatch.setattr("invoke.terminals.fcntl", mock.Mock(ioctl=fake_ioctl))

    # Pretend we are a TTY with a fileno, on a non-Windows platform
    fake_input = mock.Mock()
    fake_input.fileno.return_value = 7
    monkeypatch.setattr("invoke.terminals.isatty", lambda x: True)
    monkeypatch.setattr("invoke.terminals.has_fileno", lambda x: True)
    monkeypatch.setattr("invoke.terminals.WINDOWS", False)

    result = bytes_to_read(fake_input)

    # Buffer must be 4 bytes (sizeof C int) — not 2 — for Python 3.14
    assert captured.get("len") == 4, (
        f"FIONREAD buffer must be 4 bytes (C int size), got {captured.get('len')}"
    )
    # Result must be a valid int parsed from the 4-byte C int
    assert result == 42


def test_bytes_to_read_falls_back_to_1_when_not_tty(monkeypatch):
    """When input_ is not a TTY, return 1 (the documented fallback)."""
    fake_input = mock.Mock()
    monkeypatch.setattr("invoke.terminals.isatty", lambda x: False)
    monkeypatch.setattr("invoke.terminals.has_fileno", lambda x: True)
    monkeypatch.setattr("invoke.terminals.WINDOWS", False)
    assert bytes_to_read(fake_input) == 1


def test_bytes_to_read_handles_zero_bytes(monkeypatch):
    """FIONREAD may return 0 (nothing to read). bytes_to_read should return 0."""

    def fake_ioctl(fd, request, buf, *args, **kwargs):
        return struct.pack("i", 0)

    monkeypatch.setattr("invoke.terminals.fcntl", mock.Mock(ioctl=fake_ioctl))
    fake_input = mock.Mock()
    fake_input.fileno.return_value = 7
    monkeypatch.setattr("invoke.terminals.isatty", lambda x: True)
    monkeypatch.setattr("invoke.terminals.has_fileno", lambda x: True)
    monkeypatch.setattr("invoke.terminals.WINDOWS", False)
    assert bytes_to_read(fake_input) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
