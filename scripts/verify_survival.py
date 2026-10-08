"""Live normal-world tests. Requires launch.py --world normal --test-input.

Uses Blender's actual modal input handler and Minecraft's chat/screens. The
isolated development save is modified; this is not a test for personal saves.
"""
import json
import math
import time
from verify_runtime import ROOT, send, state, wait_for, key

RESULTS = []


def check(name, function):
    try:
        evidence = function()
        RESULTS.append({'name':name,'passed':True,'evidence':evidence})
        print('PASS',name,evidence,flush=True)
    except Exception as exc:
        RESULTS.append({'name':name,'passed':False,'error':str(exc)})
        print('FAIL',name,exc,flush=True)
    finally:
        (ROOT/'artifacts'/'survival-tests.json').write_text(json.dumps(RESULTS,indent=2))


def event(kind, value='PRESS', **kwargs):
    send('blender_event',event={'type':kind,'value':value,**kwargs})


def press(kind, **kwargs):
    event(kind,**kwargs)
    time.sleep(0.15)
    event(kind,'RELEASE',**kwargs)


def command(text, predicate=None, timeout=30):
    # Commands traverse the normal chat UI; wait for its real server response.
    path = ROOT/'logs'/'minecraft-build.log'
    offset = path.stat().st_size
    send('command',text=text)
    deadline = time.monotonic()+timeout
    response = ''
    while time.monotonic()<deadline:
        with path.open(encoding='utf8',errors='replace') as stream:
            stream.seek(offset)
            lines = stream.read()
        response = next((line for line in lines.splitlines() if 'System chat:' in line or '[System] [CHAT]' in line),response)
        if response and (predicate is None or predicate(state())):
            return response
        time.sleep(0.2)
    raise AssertionError(f'Command {text!r} timed out; response={response!r}; state={state()}')


def captured_inventory():
    s = wait_for(lambda s:s['alive'] and s['environment'].get('vanilla') and s['sections']>0,60)
    assert not s['errors'],s['errors']
    if not s['input_captured']:
        send('capture_input')
    wait_for(lambda s:s['input_captured'])
    press('E')
    opened = wait_for(lambda s:s['environment'].get('screen')=='InventoryScreen')
    send('capture_window',name='survival-inventory')
    press('E')
    wait_for(lambda s:s['environment'].get('screen')=='')
    return {'screen':opened['environment']['screen'],'host':'Blender modal operator','health':opened['environment']['health']}


def prepare():
    wait_for(lambda s:s['alive'] and s['environment'].get('vanilla') and s['sections']>0,60)
    if state()['environment'].get('screen')=='DeathScreen':
        key(43)
        key(40)
        wait_for(lambda s:s['environment'].get('health',0)>0 and s['environment'].get('screen')=='')
    command('difficulty peaceful')
    command('time set day')
    command('gamemode survival',lambda s:s['environment'].get('gameMode')=='survival')
    command('tp @s -29.5 69 -6.5')
    while state()['player']['camera_mode']:
        before = state()['player']['camera_mode']
        key(62)
        wait_for(lambda s:s['player']['camera_mode']!=before)
    return {'isolated_test_save':True,'difficulty':'peaceful'}


def third_person():
    press('F5')
    behind = wait_for(lambda s:s['player']['camera_mode']==1)
    press('F5')
    wait_for(lambda s:s['player']['camera_mode']==2)
    send('capture_window',name='third-person-in-blender')
    press('F5')
    wait_for(lambda s:s['player']['camera_mode']==0)
    return {'camera_modes':[1,2,0],'distance':behind['player']['camera_distance']}


def pause():
    press('ESC')
    opened = wait_for(lambda s:s['environment'].get('screen')=='PauseScreen' and s['environment'].get('paused'))
    tick = opened['environment']['gameTime']
    time.sleep(2.5)
    assert state()['environment']['gameTime']==tick
    press('ESC')
    wait_for(lambda s:s['environment'].get('screen')=='' and not s['environment'].get('paused'))
    return {'gameTime_stopped':tick}


def dimensions():
    command('gamemode spectator',lambda s:s['environment'].get('gameMode')=='spectator')
    output = []
    for dimension,position in [('the_nether',(0,90,0)),('the_end',(0,90,0)),('overworld',(-29.5,90,-6.5))]:
        before = state()['render_messages'].get('3',0)
        command(f'execute in minecraft:{dimension} run tp @s {position[0]} {position[1]} {position[2]}',
                lambda s:s['environment'].get('dimension')=='minecraft:'+dimension,60)
        current = wait_for(lambda s:s['render_messages'].get('3',0)>before and s['sections']>10,60)
        assert math.dist(current['position'],position)<1.0,(current['position'],position)
        send('capture_window',name=dimension+'-in-blender')
        output.append({'dimension':dimension,'sections':current['sections'],'position':current['position'],
                       'clear_messages':current['render_messages']['3']})
    command('tp @s -29.5 69 -6.5')
    command('gamemode survival',lambda s:s['environment'].get('gameMode')=='survival')
    return output


def death_respawn():
    command('kill',lambda s:s['environment'].get('screen')=='DeathScreen')
    dead = state()
    assert dead['environment']['health']==0
    send('capture_window',name='death-screen-in-blender')
    time.sleep(1.5) # Vanilla briefly disables the respawn button.
    press('TAB')
    press('RET')
    alive = wait_for(lambda s:s['environment'].get('screen')=='' and s['environment'].get('health',0)>0,30)
    assert alive['position'][1]>40,alive['position']
    return {'dead_health':0,'respawn_health':alive['environment']['health'],'natural_spawn':alive['position']}


def release():
    press('ESC',shift=True)
    s = wait_for(lambda s:not s['input_captured'])
    assert not s['errors'],s['errors']
    return {'input_captured':s['input_captured'],'errors':s['errors']}


if __name__ == '__main__':
    check('Prepare isolated vanilla test world',prepare)
    check('Real Blender keyboard opens vanilla inventory',captured_inventory)
    check('F5 cycles three camera modes',third_person)
    check('Escape pauses vanilla singleplayer',pause)
    check('Dimension transitions replace native geometry and preserve destinations',dimensions)
    check('Death screen and natural respawn through Blender input',death_respawn)
    check('Shift Escape releases Blender input',release)
    send('capture_window',name='survival-world-in-blender')
    if any(not item['passed'] for item in RESULTS):
        raise SystemExit(1)
