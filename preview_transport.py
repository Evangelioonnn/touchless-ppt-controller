"""Bounded, latest-frame BGR transport in this Windows user's local session.

No files, network, frame queue or base64. The native view owns the mapping;
an odd/even sequence prevents readers from displaying a partially copied frame.
"""
from __future__ import annotations
import mmap
import re
import struct
import time

CAPACITY = 8 * 1024 * 1024
PAYLOAD_OFFSET = 64
HEADER = struct.Struct('<4sIqIIIId')
MAGIC = b'TPV1'


class FramePublisher:
    def __init__(self, name: str, mapping=None):
        if not re.fullmatch(r'Local\\TouchlessPPTPreview\.[0-9a-f]{32}', name):
            raise ValueError('Invalid local preview channel name.')
        self.mapping = mapping if mapping is not None else mmap.mmap(-1, CAPACITY, tagname=name)
        self.sequence = 0
        self.closed = False

    def publish(self, image, published_at: float | None = None) -> None:
        if self.closed:
            return
        if image.ndim != 3 or image.shape[2] != 3 or str(image.dtype) != 'uint8':
            raise ValueError('Preview must be an 8-bit three-channel BGR image.')
        height, width = image.shape[:2]
        stride = width * 3
        length = height * stride
        if width <= 0 or height <= 0 or width > 4096 or height > 2160 or length > CAPACITY - PAYLOAD_OFFSET:
            raise ValueError('Preview exceeds the bounded channel capacity.')
        sequence = self.sequence + 2
        self.mapping[8:16] = struct.pack('<q', sequence - 1)
        header = HEADER.pack(MAGIC, 1, sequence - 1, width, height, stride, length,
                             time.perf_counter() if published_at is None else published_at)
        self.mapping[:HEADER.size] = header
        self.mapping[PAYLOAD_OFFSET:PAYLOAD_OFFSET + length] = image.tobytes(order='C')
        self.mapping[8:16] = struct.pack('<q', sequence)
        self.sequence = sequence

    def close(self):
        self.closed = True
        close = getattr(self.mapping, 'close', None)
        if close is not None:
            close()
