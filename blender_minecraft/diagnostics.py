"""Explicit local test controls and viewport captures; no arbitrary code execution."""
import json
from pathlib import Path
import struct
import zlib
import gpu
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def controls(session):
    inbox = ROOT/'.local'/'control'
    if not inbox.exists():
        return
    for path in sorted(inbox.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf8'))
        action = data['action']
        if action == 'command':
            session.command(data['text'])
        elif action == 'input':
            session.link.input(data['kind'],data.get('code',0),data.get('a',0),data.get('b',0),data.get('c',0))
        elif action == 'look':
            session.yaw,session.pitch = data['yaw'],data['pitch']
        elif action == 'settings':
            allowed = {'frustum_culling','camera_view','show_minecraft','environment'}
            for name,value in data['values'].items():
                if name not in allowed:
                    raise ValueError(f'Unsupported diagnostic setting: {name}')
                setattr(session.scene.mciblender,name,value)
        elif action == 'capture_input':
            import bpy
            with bpy.context.temp_override(window=session.window,area=session.area,region=session.region):
                bpy.ops.mciblender.capture('INVOKE_DEFAULT')
        elif action == 'quit_game':
            import bpy
            with bpy.context.temp_override(window=session.window,area=session.area,region=session.region):
                bpy.ops.mciblender.quit_game()
        elif action == 'blender_event':
            session.window.event_simulate(**data['event'])
        elif action == 'capture':
            session.capture_name = Path(data['name']).stem
        elif action == 'capture_window':
            import bpy
            output = ROOT/'artifacts'/'captures'
            output.mkdir(parents=True,exist_ok=True)
            bpy.ops.screen.screenshot(filepath=str(output/(Path(data['name']).stem+'.png')))
        elif action == 'teleport':
            session.position = tuple(data['position'])
            session.requested_position = session.position
            session.teleport += 1
        elif action == 'shutdown':
            import bpy
            session.close()
            bpy.ops.wm.quit_blender()
        else:
            raise ValueError(f'Unknown diagnostic action: {action}')
        path.unlink()


def capture(region, name):
    x,y,w,h = gpu.state.viewport_get()
    raw = gpu.state.active_framebuffer_get().read_color(x,y,w,h,4,0,'UBYTE')
    raw.dimensions = (w*h*4,)
    pixels = bytes(raw.to_list())
    rows = [pixels[i*w*4:(i+1)*w*4] for i in range(h-1,-1,-1)]
    def chunk(tag,data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xFFFFFFFF)
    png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))
    png += chunk(b'IDAT',zlib.compress(b''.join(b'\0'+r for r in rows)))+chunk(b'IEND',b'')
    output = ROOT/'artifacts'/'captures'
    output.mkdir(parents=True,exist_ok=True)
    (output/(name+'.png')).write_bytes(png)
