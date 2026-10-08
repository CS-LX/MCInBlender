"""Live daylight, night vision, precipitation and dimension presentation checks."""
import json
import time
from verify_runtime import ROOT,send,state,wait_for
from verify_survival import command


def atmosphere(s):
    return s['environment'].get('atmosphere',{})


def record(results,name):
    s = state()
    assert not s['errors'],s['errors']
    a = atmosphere(s)
    results.append({'name':name,'passed':True,'atmosphere':{k:v for k,v in a.items() if 'Columns' not in k},
                    'rain_columns':len(a.get('rainColumns',[])),'snow_columns':len(a.get('snowColumns',[])),
                    'lightmap':s['lightmap_samples'],'textures':s['environment_textures']})
    (ROOT/'artifacts/environment-tests.json').write_text(json.dumps(results,indent=2))
    print('PASS',name,'lightmap=',s['lightmap_samples'],'sky=',a.get('skyColor'),flush=True)
    send('capture_window',name='environment-'+name)
    time.sleep(1)
    return s


def main():
    results = []
    initial = wait_for(lambda s:s['alive'] and len(s.get('environment_textures',[]))==5 and s.get('lightmap_samples') and s['sections']>2000,120)
    assert not initial['errors'],initial['errors']
    position = initial['position']
    mode = initial['environment']['gameMode']
    view = initial['camera_view']
    command('weather clear')
    command('time set noon')
    wait_for(lambda s:atmosphere(s).get('skyFactor',0)>0.95)
    time.sleep(2)
    day = record(results,'day')
    command('time set midnight')
    wait_for(lambda s:sum(s['lightmap_samples']['sky'][:3])<sum(day['lightmap_samples']['sky'][:3])*0.8)
    night = record(results,'night')
    assert sum(atmosphere(night)['skyColor'])<sum(atmosphere(day)['skyColor'])*0.5
    command('effect give @s minecraft:night_vision 60 0 true')
    wait_for(lambda s:sum(s['lightmap_samples']['sky'][:3])>sum(night['lightmap_samples']['sky'][:3])*1.3)
    record(results,'night-vision')
    command('effect clear @s minecraft:night_vision')
    command('time set noon')
    command('weather rain')
    wait_for(lambda s:atmosphere(s).get('rain',0)>0.8 and len(atmosphere(s).get('rainColumns',[]))>10,40)
    record(results,'rain')
    command('weather clear')
    command('gamemode spectator',lambda s:s['environment'].get('gameMode')=='spectator')
    send('settings',values={'camera_view':'FIRST'})
    command('tp @s 256.0 140.0 256.0')
    time.sleep(5)
    command('fillbiome 248 96 248 264 160 264 minecraft:snowy_plains')
    command('weather rain')
    wait_for(lambda s:atmosphere(s).get('rain',0)>0.8 and len(atmosphere(s).get('snowColumns',[]))>10,40)
    record(results,'snow')
    command('weather clear')
    for dimension in ('the_nether','the_end'):
        command(f'execute in minecraft:{dimension} run tp @s 0.0 90.0 0.0',lambda s:s['environment'].get('dimension')=='minecraft:'+dimension,60)
        wait_for(lambda s:s['sections']>30 and atmosphere(s).get('skybox')==('NONE' if dimension=='the_nether' else 'END'),60)
        time.sleep(2)
        record(results,dimension)
    command('execute in minecraft:overworld run tp @s '+' '.join(str(x) for x in position),lambda s:s['environment'].get('dimension')=='minecraft:overworld',60)
    command('gamemode '+mode,lambda s:s['environment'].get('gameMode')==mode)
    wait_for(lambda s:atmosphere(s).get('skybox')=='OVERWORLD' and s['sections']>30,60)
    record(results,'returned-overworld')
    send('look',yaw=0,pitch=-89)
    command('time set noon')
    time.sleep(2)
    record(results,'sun')
    command('time set midnight')
    time.sleep(2)
    record(results,'moon')
    command('time set noon')
    send('look',yaw=initial['yaw'],pitch=initial['pitch'])
    send('settings',values={'camera_view':view})
    print('PASS all environment checks',flush=True)


if __name__=='__main__':
    main()
