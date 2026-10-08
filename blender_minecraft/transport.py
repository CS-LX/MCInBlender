"""Blender owns the SkyCraft mapping. All ring producers check back pressure.

Atomic Windows operations are used for the triple-buffer ownership exchange;
ordinary load/store is insufficient because the Java writer can exchange too.
"""
import ctypes
import mmap
import os
import struct
import time
from pathlib import Path
from . import protocol as P


class HostLink:
    def __init__(self, name=P.NAME):
        if os.name != 'nt':
            raise OSError('The SkyCraft shared-memory transport requires Windows')
        self.k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k32.GetTickCount64.restype = ctypes.c_uint64
        self.k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self.k32.CreateMutexW.restype = ctypes.c_void_p
        self.k32.CloseHandle.argtypes = [ctypes.c_void_p]
        dll = Path(__file__).resolve().parents[1]/'.local'/'native'/'mc_atomic.dll'
        if not dll.exists():
            dll = Path(__file__).resolve().parent/'bin'/'mc_atomic.dll'
        self.atomic = ctypes.CDLL(str(dll))
        self.atomic.mc_exchange32.argtypes = [ctypes.c_void_p,ctypes.c_int32]
        self.atomic.mc_exchange32.restype = ctypes.c_int32
        self.atomic.mc_exchange64.argtypes = [ctypes.c_void_p,ctypes.c_int64]
        self.atomic.mc_exchange64.restype = ctypes.c_int64
        self.atomic.mc_load64.argtypes = [ctypes.c_void_p]
        self.atomic.mc_load64.restype = ctypes.c_int64
        self.mutex = self.k32.CreateMutexW(None, False, name + '_blender_owner')
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            self.k32.CloseHandle(self.mutex)
            self.mutex = None
            raise RuntimeError('A Blender host already owns this session')
        self.m = mmap.mmap(-1, P.SIZE, tagname=name)
        self.address = ctypes.addressof(ctypes.c_char.from_buffer(self.m))
        for base, n in [(0, 0x1000), (P.INPUT, 0x80), (P.ACTORS, 0x40),
                        (P.EVENTS, 0x80), (P.ENTITIES, 0x40), (P.COLLISION, 0x80), (P.RENDER, 0x80)]:
            self.m[base:base+n] = bytes(n)
        struct.pack_into('<IIII', self.m, 0, P.MAGIC, P.VERSION, os.getpid(), 0)
        self.front, self.seq = 2, 0
        self.closed = False
        # Stay offline until Session publishes its first complete state. A live
        # zero-filled state can teleport an already running client underground.

    def atomic_load64(self, offset):
        return self.atomic.mc_load64(self.address + offset)

    def store64(self, offset, value):
        self.atomic.mc_exchange64(self.address + offset, value)

    def heartbeat(self):
        self.store64(0x10, self.k32.GetTickCount64())

    @property
    def alive(self):
        beat = self.atomic_load64(0x18)
        return beat > 0 and 0 <= self.k32.GetTickCount64() - beat < 5000

    def state(self, position=(0, 100, 0), yaw=0, pitch=0, width=1280, height=720,
              teleport=1, epoch=1, world=0x3C, flags=1, hour=12):
        width, height = max(64, min(3840, int(width))), max(64, min(2160, int(height)))
        self.seq = (self.seq + 2) & 0xFFFFFFFE
        self.atomic.mc_exchange32(self.address + P.SKY, self.seq - 1)
        struct.pack_into('<IIIdddffIIIf', self.m, P.SKY + 4, flags, world, epoch,
                         *position, yaw, pitch, teleport, width, height, hour)
        self.atomic.mc_exchange32(self.address + P.SKY, self.seq)

    def snapshot(self, base, size):
        for _ in range(8):
            before, = struct.unpack_from('<I', self.m, base)
            if before == 0 or before & 1:
                continue
            raw = self.m[base:base+size]
            after, = struct.unpack_from('<I', self.m, base)
            if before == after:
                return raw
        return None

    def player(self):
        raw = self.snapshot(P.MC, 0xC8)
        return P.decode_player(raw) if raw else None

    def input(self, kind, code=0, a=0, b=0, c=0):
        head, tail = self.atomic_load64(P.INPUT), self.atomic_load64(P.INPUT+0x40)
        if not (0 <= head-tail < 4096):
            raise BufferError('Minecraft input queue is full')
        struct.pack_into('<HHiii', self.m, P.INPUT+0x80+(head % 4096)*16, kind, code, a, b, c)
        self.store64(P.INPUT, head+1)

    def send_collision(self, kind, payload):
        base, size = P.COLLISION, P.COLLISION_BYTES - 0x80
        head, tail = self.atomic_load64(base), self.atomic_load64(base+0x40)
        msg = (8 + len(payload) + 7) & ~7
        pos = head % size
        pad = size-pos if pos+msg > size else 0
        if msg > size//2:
            raise P.ProtocolError('Collision message too large')
        if size-(head-tail) < msg+pad:
            return False
        if pad:
            struct.pack_into('<II', self.m, base+0x80+pos, 0, 0)
            head += pad
            pos = 0
        at = base+0x80+pos
        struct.pack_into('<II', self.m, at, kind, len(payload))
        self.m[at+8:at+8+len(payload)] = payload
        self.store64(base, head+msg)
        return True

    def render_messages(self, budget_ms=8):
        base, size = P.RENDER, P.RENDER_BYTES - 0x80
        head, tail = self.atomic_load64(base), self.atomic_load64(base+0x40)
        if not 0 <= head-tail <= size:
            raise P.ProtocolError('Render ring overrun')
        deadline = time.perf_counter() + budget_ms / 1000
        while tail < head and time.perf_counter() < deadline:
            pos = tail % size
            kind, n = struct.unpack_from('<II', self.m, base+0x80+pos)
            if kind == 0:
                tail += size-pos
                self.store64(base+0x40, tail)
                continue
            msg = (8+n+7) & ~7
            if n > size//2 or pos+msg > size or tail+msg > head:
                raise P.ProtocolError('Invalid render record length')
            payload = self.m[base+0x88+pos:base+0x88+pos+n]
            tail += msg
            self.store64(base+0x40, tail)
            yield kind, payload

    def events(self):
        head, tail = self.atomic_load64(P.EVENTS), self.atomic_load64(P.EVENTS+0x40)
        if not 0 <= head-tail <= 512:
            raise P.ProtocolError('Event ring overrun')
        result = []
        while tail < head:
            result.append(struct.unpack_from('<IIffffII', self.m, P.EVENTS+0x80+(tail%512)*32))
            tail += 1
        self.store64(P.EVENTS+0x40, tail)
        return result

    def overlay(self):
        state, = struct.unpack_from('<I', self.m, P.OVERLAY)
        if not state & 4:
            return None
        state = self.atomic.mc_exchange32(self.address+P.OVERLAY, self.front)
        self.front = state & 3
        if self.front >= 3:
            raise P.ProtocolError('Invalid overlay slot')
        at = P.OVERLAY_HEADERS + self.front*0x40
        width, height, flags = struct.unpack_from('<III', self.m, at)
        frame, = struct.unpack_from('<Q', self.m, at+0x10)
        if not (0 < width <= 3840 and 0 < height <= 2160):
            raise P.ProtocolError('Invalid overlay dimensions')
        start = P.PIXELS+self.front*P.SLOT_BYTES
        return width, height, flags, frame, self.m[start:start+width*height*4]

    def close(self):
        if self.closed:
            return
        try:
            self.input(6)
        except BufferError:
            pass
        self.store64(0x10, 0)
        self.m.close()
        self.k32.CloseHandle(self.mutex)
        self.closed = True
