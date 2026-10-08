"""SkyCraft v11 wire definitions. No Blender dependency; little-endian Windows x64."""
import math
import struct
from dataclasses import dataclass

MAGIC, VERSION = 0x43594B53, 11
NAME = r"Local\MCInBlender_SkyCraft_v11"
SKY, MC, OVERLAY, OVERLAY_HEADERS = 0x100, 0x200, 0x300, 0x340
INPUT, ACTORS, EVENTS, ENTITIES = 0x1000, 0x12000, 0x17000, 0x1C000
COLLISION, COLLISION_BYTES = 0x20000, 32 << 20
PIXELS = COLLISION + COLLISION_BYTES
SLOT_BYTES = 3840 * 2160 * 4
RENDER = PIXELS + 3 * SLOT_BYTES
RENDER_BYTES = 64 << 20
SIZE = RENDER + RENDER_BYTES
VERTEX = struct.Struct('<5f4BII')


class ProtocolError(ValueError):
    pass


def mc_to_blender(p):
    return (p[0], -p[2], p[1])


def blender_to_mc(p):
    return (p[0], p[2], -p[1])


@dataclass(frozen=True)
class Player:
    flags: int
    position: tuple
    yaw: float
    pitch: float
    eye_height: float
    sensitivity: float
    teleport_ack: int
    gui_scale: int
    frame: int
    fov: float
    eye: tuple
    camera_mode: int
    camera_distance: float

    @property
    def in_world(self):
        return bool(self.flags & 1)

    @property
    def screen_open(self):
        return bool(self.flags & 2)


def decode_player(raw):
    if len(raw) < 0xC8:
        raise ProtocolError('Short player state')
    values = struct.unpack_from('<IIdddffffIIQfffIddd', raw)
    mode, distance = struct.unpack_from('<If', raw, 0xC0)
    p = Player(values[1], values[2:5], values[5], values[6], values[7], values[8],
               values[9], values[10], values[11], values[12], values[16:19], mode, distance)
    if not all(math.isfinite(x) for x in (*p.position, *p.eye, p.fov, p.yaw, p.pitch)):
        raise ProtocolError('Nonfinite player state')
    return p


def texture_payload(kind, payload):
    """Return texture id, dimensions and immutable RGBA pixels, after bounds validation."""
    header = 8 if kind == 1 else 16
    if len(payload) < header:
        raise ProtocolError('Short texture header')
    if kind == 1:
        width, height = struct.unpack_from('<II', payload)
        ident = 0
    else:
        ident, width, height, _ = struct.unpack_from('<IIII', payload)
    if not (0 < width <= 16384 and 0 < height <= 16384):
        raise ProtocolError('Invalid texture dimensions')
    if len(payload) != header + width * height * 4:
        raise ProtocolError('Texture byte count mismatch')
    return ident, width, height, payload[header:]


def mesh_payload(kind, payload):
    """Return origin, batches (texture/first/count/flags), packed triangle vertices."""
    if kind == 2:
        if len(payload) < 16:
            raise ProtocolError('Short section header')
        sx, sy, sz, count = struct.unpack_from('<iiiI', payload)
        origin, batches, offset = (sx * 16, sy * 16, sz * 16), [(0, 0, count, 0)], 16
    else:
        offset = 24 if kind == 6 else 0
        if len(payload) < offset + 8:
            raise ProtocolError('Short dynamic mesh header')
        origin = struct.unpack_from('<ddd', payload) if kind == 6 else (0, 0, 0)
        n, count = struct.unpack_from('<II', payload, offset)
        offset += 8
        if n > 65536 or offset + n * 16 > len(payload):
            raise ProtocolError('Invalid batch count')
        batches = [struct.unpack_from('<IIII', payload, offset + i * 16) for i in range(n)]
        offset += n * 16
    if count % 3 or len(payload) != offset + count * 32:
        raise ProtocolError('Triangle byte count mismatch')
    if any(first + size > count or first % 3 or size % 3 for _, first, size, _ in batches):
        raise ProtocolError('Batch exceeds vertices')
    return origin, batches, payload[offset:]
