"""Exercise the running Blender-hosted game through the same SkyCraft input ring.

This verifies a live developer instance; it does not simulate Minecraft responses.
Run after launch.py. Test worlds are isolated under minecraft/run/.
"""
import json
import math
from pathlib import Path
import time
import uuid
import itertools

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT/'.local'/'control'
RESULTS = []
SEQUENCE = itertools.count()


def send(action, **kwargs):
    INBOX.mkdir(parents=True,exist_ok=True)
    path = INBOX/(f'{time.monotonic_ns():020d}-{next(SEQUENCE):08d}-{uuid.uuid4().hex}.json')
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'action':action,**kwargs}),encoding='utf8')
    temp.rename(path)


def state():
    return json.loads((ROOT/'logs'/'host-status.json').read_text())


def wait_for(predicate, timeout=12):
    end = time.monotonic()+timeout
    while time.monotonic()<end:
        s = state()
        if predicate(s):
            return s
        time.sleep(0.15)
    raise AssertionError('Runtime condition timed out: '+json.dumps(state()))


def key(code, duration=0.15):
    send('input',kind=1,code=code,a=1)
    time.sleep(duration)
    send('input',kind=1,code=code,a=0)


def check(name, function):
    try:
        result = function()
        RESULTS.append({'name':name,'passed':True,'evidence':result})
        print('PASS',name,result,flush=True)
    except Exception as exc:
        RESULTS.append({'name':name,'passed':False,'error':str(exc)})
        print('FAIL',name,exc,flush=True)
    finally:
        (ROOT/'artifacts').mkdir(exist_ok=True)
        (ROOT/'artifacts'/'runtime-tests.json').write_text(json.dumps(RESULTS,indent=2))


def connected():
    s = wait_for(lambda s:s['alive'] and s['player'] and s['player']['flags']&1)
    assert not s['errors'],s['errors']
    return {'host':s['host'],'overlay_frame':s['overlay_frame'],'sections':s['sections'],'textures':s['textures']}


def walk():
    send('look',yaw=0,pitch=12)
    p0 = state()['position']
    key(26,0.4)
    moved = wait_for(lambda s:math.dist(s['position'],p0)>0.3)
    p1 = moved['position']
    assert abs(p1[1]-p0[1])<0.2,(p0,p1)
    key(22,0.4)
    return {'before':p0,'after_forward':p1,'floor_height_unchanged':True}


def inventory():
    key(8)
    opened = wait_for(lambda s:s['player']['flags']&2)
    send('capture_window',name='inventory-in-blender')
    time.sleep(1)
    key(8)
    closed = wait_for(lambda s:not s['player']['flags']&2)
    return {'open_flags':opened['player']['flags'],'closed_flags':closed['player']['flags']}


def place():
    send('look',yaw=0,pitch=55)
    key(35) # hotbar slot 6: upstream starter planks
    time.sleep(1)
    before = state()['render_messages'].get('2',0)
    send('input',kind=2,code=3,a=1)
    time.sleep(0.15)
    send('input',kind=2,code=3,a=0)
    changed = wait_for(lambda s:s['render_messages'].get('2',0)>before)
    send('capture_window',name='placed-block-in-blender')
    time.sleep(0.5)
    return {'section_updates_before':before,'section_updates_after':changed['render_messages']['2']}


def break_block():
    before = state()['render_messages'].get('2',0)
    send('input',kind=2,code=1,a=1)
    time.sleep(0.2)
    send('input',kind=2,code=1,a=0)
    changed = wait_for(lambda s:s['render_messages'].get('2',0)>before)
    send('look',yaw=0,pitch=12)
    return {'section_updates_before':before,'section_updates_after':changed['render_messages']['2']}


if __name__ == '__main__':
    check('Blender owns live Minecraft rendering',connected)
    check('Walk on native Blender ground',walk)
    check('Open and close real inventory through host input',inventory)
    check('Place Minecraft block on Blender ground',place)
    check('Break placed block',break_block)
    send('capture_window',name='verified-host')
    if any(not r['passed'] for r in RESULTS):
        raise SystemExit(1)
