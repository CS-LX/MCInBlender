"""Travel beyond render distance and back; verify old geometry is evicted.

Requires a running normal-mode developer session with --test-input. Changes only
the isolated development save. Restores player position, mode and view afterward.
"""
import json
import math
import time
from verify_runtime import ROOT, send, state, wait_for
from verify_survival import command, press


def main():
    initial = wait_for(lambda s:s['alive'] and s['environment'].get('vanilla') and s.get('section_extent'),90)
    position = initial['position']
    mode = initial['environment']['gameMode']
    view = initial['camera_view']
    records = []
    try:
        command('gamemode spectator',lambda s:s['environment'].get('gameMode')=='spectator')
        send('settings',values={'camera_view':'FIRST'})
        for name,target in [('east',(1040,140,4)),('west',(-1040,140,4)),('return',position)]:
            command('tp @s '+' '.join(f'{v:.6f}' for v in target),lambda s:math.dist(s['position'],target)<0.2)
            cx,cz = math.floor(target[0]/16),math.floor(target[2]/16)
            def settled(s):
                extent = s.get('section_extent')
                return (s['sections']>100 and extent and
                        cx-32<extent[0][0]<=extent[0][1]<cx+32 and
                        cz-32<extent[2][0]<=extent[2][1]<cz+32 and
                        s['performance'].get('pending_meshes',99)<10)
            current = wait_for(settled,120)
            time.sleep(5)
            current = state()
            assert settled(current),current['section_extent']
            assert not current['errors'],current['errors']
            entry = {'name':name,'passed':True,'position':current['position'],'sections':current['sections'],
                     'section_extent':current['section_extent'],'retained_records':current['section_records']}
            records.append(entry)
            print('PASS streaming',entry,flush=True)
        # HUD was skipped during free editing; real capture must upload the latest UI.
        send('settings',values={'camera_view':'BLENDER'})
        wait_for(lambda s:s['camera_view']=='BLENDER' and not s['input_captured'])
        time.sleep(3)
        previous = state()['overlay_frame']
        send('capture_input')
        wait_for(lambda s:s['input_captured'] and s['overlay_frame']>previous)
        press('E')
        inventory = wait_for(lambda s:s['environment'].get('screen')=='InventoryScreen')
        send('capture_window',name='optimized-inventory')
        press('E')
        wait_for(lambda s:s['environment'].get('screen')=='')
        press('ESC',shift=True)
        wait_for(lambda s:not s['input_captured'])
        records.append({'name':'HUD resumes after free editing and real Blender inventory opens',
                        'passed':True,'screen':inventory['environment']['screen'],'overlay_frame':inventory['overlay_frame']})
    finally:
        command('tp @s '+' '.join(str(v) for v in position))
        command('gamemode '+mode,lambda s:s['environment'].get('gameMode')==mode)
        send('settings',values={'camera_view':view})
        (ROOT/'artifacts/streaming-tests.json').write_text(json.dumps(records,indent=2))
    print('PASS all streaming and overlay regressions',flush=True)


if __name__ == '__main__':
    main()
