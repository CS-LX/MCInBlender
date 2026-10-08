"""Combat, enchanting and real portal travel through Blender's modal input.

Requires an isolated normal-world developer session with --test-input. Replaces
the test inventory and edits an arena near (64,100,64). Commands prepare fixtures
and read server evidence; attacks, item use, menus and portal entry use real input.
"""
import argparse
import json
import math
import re
import time
from verify_runtime import ROOT,send,state,wait_for
from verify_survival import command,event,press
from verify_gameplay import wait_env,look_at,open_block,select_item,item_slot,click_slot,close_screen,assert_block

RESULTS = []


def check(name, function):
    try:
        evidence = function()
        assert not state()['errors'],state()['errors']
        RESULTS.append({'name':name,'passed':True,'evidence':evidence})
        print('PASS',name,evidence,flush=True)
    except Exception as exc:
        RESULTS.append({'name':name,'passed':False,'error':str(exc)})
        print('FAIL',name,exc,flush=True)
        raise
    finally:
        (ROOT/'artifacts').mkdir(exist_ok=True)
        (ROOT/'artifacts/adventure-tests.json').write_text(json.dumps(RESULTS,indent=2))


def hold(button, seconds):
    event(button)
    try:
        time.sleep(seconds)
    finally:
        event(button,'RELEASE')


def teleport(position):
    command('tp @s '+' '.join(str(v) for v in position),lambda s:math.dist(s['position'],position)<0.2)


def number_query(text):
    response = command(text)
    found = re.search(r'following entity data: (-?\d+(?:\.\d+)?)',response)
    assert found,response
    return float(found.group(1))


def health(tag):
    return number_query(f'data get entity @e[tag={tag},limit=1] Health')


def spawn(kind, tag, position, no_ai=True):
    command('summon minecraft:'+kind+' '+' '.join(map(str,position))+
            ' {Tags:["mciblender_adventure","'+tag+'"],PersistenceRequired:1b,NoAI:'+('1b' if no_ai else '0b')+'}')


def prepare():
    wait_for(lambda s:s['alive'] and s['environment'].get('vanilla') and s['sections']>50,90)
    assert state()['environment']['dimension']=='minecraft:overworld','Start this test in the Overworld'
    if state()['environment']['screen']:
        press('ESC')
    command('difficulty peaceful')
    command('weather clear')
    command('time set noon')
    command('gamemode creative')
    command('kill @e[tag=mciblender_adventure]')
    command('fill 54 99 54 78 99 80 minecraft:stone')
    command('fill 54 100 54 78 110 80 minecraft:air')
    teleport((64.5,100.0,64.5))
    command('clear')
    for item,count in [('diamond_sword',1),('bow',1),('arrow',16),('flint_and_steel',1),('lapis_lazuli',3)]:
        command(f'give @s minecraft:{item} {count}')
    command('gamemode survival',lambda s:s['environment']['gameMode']=='survival')
    send('settings',values={'camera_view':'FIRST'})
    if not state()['input_captured']:
        send('capture_input')
    wait_for(lambda s:s['input_captured'] and s['player']['camera_mode']==0)
    return {'arena':[54,99,54,78,110,80],'host_input':'Blender modal operator','mode':'survival'}


def melee():
    teleport((64.5,100.0,64.5))
    spawn('cow','mciblender_melee',(64.5,100,66.5))
    select_item('diamond_sword')
    look_at((64.5,100.9,66.5))
    wait_env(lambda e:e.get('targetEntity',{}).get('type')=='minecraft:cow')
    before = health('mciblender_melee')
    press('LEFTMOUSE')
    time.sleep(1)
    after = health('mciblender_melee')
    assert 0<after<before,(before,after)
    send('capture_window',name='adventure-melee-in-blender')
    press('LEFTMOUSE')
    time.sleep(1)
    marker = 'MCIBLENDER_MELEE_KILLED'
    response = command('execute unless entity @e[tag=mciblender_melee] run say '+marker)
    assert marker in response,response
    return {'server_health_before':before,'after_first_sword_click':after,'second_sword_click_killed':True}


def bow():
    teleport((64.5,100.0,64.5))
    spawn('iron_golem','mciblender_bow',(64.5,100,75.5))
    select_item('bow')
    before = health('mciblender_bow')
    arrows = state()['environment']['inventory']['minecraft:arrow']
    look_at((64.5,101.6,75.5))
    event('RIGHTMOUSE')
    try:
        time.sleep(1.3)
        send('capture_window',name='adventure-bow-drawn-in-blender')
        time.sleep(0.5)
    finally:
        event('RIGHTMOUSE','RELEASE')
    wait_env(lambda e:e['inventory'].get('minecraft:arrow')==arrows-1)
    after = health('mciblender_bow')
    assert 0<after<before,(before,after)
    command('kill @e[tag=mciblender_bow]')
    return {'server_health_before':before,'after_real_arrow':after,'arrows_consumed':1}


def damage():
    teleport((64.5,100.0,64.5))
    command('time set midnight')
    command('difficulty normal')
    command('effect give @s minecraft:instant_health 1 10 true')
    wait_env(lambda e:e['health']==20)
    spawn('zombie','mciblender_attacker',(64.5,100,66.5),no_ai=False)
    look_at((64.5,101,66.5))
    try:
        injured = wait_env(lambda e:0<e['health']<20,15)
        send('capture_window',name='adventure-zombie-damage-in-blender')
        return {'health_before':20,'health_after_hostile_attack':injured['health']}
    finally:
        command('kill @e[tag=mciblender_attacker]')
        command('difficulty peaceful')
        command('effect give @s minecraft:instant_health 1 10 true')
        command('time set noon')


def enchanting():
    teleport((64.5,100.0,64.5))
    command('setblock 64 100 67 minecraft:enchanting_table')
    command('experience set @s 30 levels',lambda s:s['environment']['experience']==30)
    open_block((64,100,67),'EnchantmentScreen')
    click_slot(item_slot('diamond_sword',2),shift=True)
    wait_env(lambda e:e['menuSlots'][0]['item']=='minecraft:diamond_sword')
    click_slot(item_slot('lapis_lazuli',2),shift=True)
    ready = wait_env(lambda e:e['menuSlots'][1]['count']==3 and e.get('enchantmentOffers',[{}])[0].get('requiredLevel',0)>0)
    send('capture_window',name='adventure-enchantment-offers-in-blender')
    # Actual button bounds verified against the running version's EnchantmentScreen.
    current = state()
    e = current['environment']
    rx,ry,rw,rh = current['viewport_region']
    x = round(rx+(e['menuLeft']+100)/e['guiWidth']*rw)
    y = round(ry+(1-(e['menuTop']+23)/e['guiHeight'])*rh)
    event('MOUSEMOVE','NOTHING',x=x,y=y)
    time.sleep(0.2)
    press('LEFTMOUSE',x=x,y=y)
    enchanted = wait_env(lambda e:e['menuSlots'][0].get('enchanted'))
    assert enchanted['experience']==29,enchanted['experience']
    assert enchanted['menuSlots'][1]['count']==2,enchanted['menuSlots'][1]
    send('capture_window',name='adventure-enchanted-sword-in-blender')
    click_slot(0,shift=True)
    wait_env(lambda e:e['menuSlots'][0]['count']==0)
    close_screen()
    select_item('diamond_sword')
    wait_env(lambda e:e['heldStack']['enchanted'])
    response = command('data get entity @s Inventory')
    assert 'minecraft:enchantments' in response,response
    return {'required_level':ready['enchantmentOffers'][0]['requiredLevel'],'xp_before':30,'xp_after':29,
            'lapis_consumed':1,'server_enchantment_component':True,'held_stack':state()['environment']['heldStack']}


def portals():
    clears_before = state()['render_messages'].get('3',0)
    command('setblock 64 100 67 minecraft:air')
    # Vanilla-sized obsidian frame; the interior starts at ground level.
    command('fill 62 99 70 65 103 70 minecraft:obsidian')
    command('fill 63 100 70 64 102 70 minecraft:air')
    command('fill 63 100 71 64 102 71 minecraft:obsidian')
    teleport((64.0,100.0,68.0))
    select_item('flint_and_steel')
    look_at((63.5,100,70.5),(63,99,70))
    press('RIGHTMOUSE')
    assert_block((63,100,70),'minecraft:nether_portal','PORTAL_LIT_WITH_ITEM')
    send('capture_window',name='adventure-portal-lit-in-blender')
    send('look',yaw=0,pitch=0)
    wait_for(lambda s:abs(s['yaw'])<0.01)
    hold('W',1.0)
    send('capture_window',name='adventure-entering-portal-in-blender')
    nether = wait_for(lambda s:s['environment']['dimension']=='minecraft:the_nether' and
                      s['environment']['screen']=='' and s['sections']>10 and
                      s['render_messages'].get('3',0)>clears_before,90)
    send('capture_window',name='adventure-nether-arrival-in-blender')
    return finish_portal_return(nether)


def finish_portal_return(nether):
    arrived = nether['position']
    assert math.dist((arrived[0],arrived[2]),(8,8.75))<128,arrived
    inside = wait_for(lambda s:'nether_portal' in s['environment'].get('feetBlock',''),15)
    entry = dict(zip(('x','y','z'),(math.floor(v) for v in inside['position'])))
    entry['state'] = inside['environment']['feetBlock']
    px,py,pz = entry['x'],entry['y'],entry['z']
    along_z = 'axis=x' in entry['state']
    # Prepare a safe walkway outside the generated destination, then walk out
    # and re-enter. No command changes dimensions during this round trip.
    if along_z:
        command(f'fill {px-2} {py-1} {pz-4} {px+2} {py-1} {pz-1} minecraft:obsidian')
        command(f'fill {px-2} {py} {pz-4} {px+2} {py+3} {pz-1} minecraft:air')
        command(f'fill {px-2} {py} {pz+1} {px+2} {py+2} {pz+1} minecraft:obsidian')
    else:
        command(f'fill {px-4} {py-1} {pz-2} {px-1} {py-1} {pz+2} minecraft:obsidian')
        command(f'fill {px-4} {py} {pz-2} {px-1} {py+3} {pz+2} minecraft:air')
        command(f'fill {px+1} {py} {pz-2} {px+1} {py+2} {pz+2} minecraft:obsidian')
    send('look',yaw=0 if along_z else -90,pitch=0)
    time.sleep(2)
    hold('S',0.7)
    outside = wait_for(lambda s:'nether_portal' not in s['environment'].get('feetBlock',''),15)
    assert outside['environment']['dimension']=='minecraft:the_nether'
    deadline = time.monotonic()+25
    while number_query('data get entity @s PortalCooldown')>0:
        assert time.monotonic()<deadline,'Portal cooldown never expired outside the portal'
        time.sleep(1)
    hold('W',1.2)
    returned = wait_for(lambda s:s['environment']['dimension']=='minecraft:overworld' and
                        s['environment']['screen']=='' and s['sections']>50 and
                        s['render_messages'].get('3',0)>nether['render_messages'].get('3',0),90)
    assert math.dist(returned['position'],(64,100,70.5))<8,returned['position']
    send('capture_window',name='adventure-portal-return-in-blender')
    return {'lit_by':'flint_and_steel via Blender right click','nether_arrival':arrived,
            'nether_portal':entry,'overworld_return':returned['position'],'both_transitions':'walked into portal',
            'world_clear_counts':[nether['render_messages']['3'],returned['render_messages']['3']]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checks',nargs='+',choices=['melee','bow','damage','enchant','portal'],
                    default=['melee','bow','damage','enchant','portal'])
    args = ap.parse_args()
    initial = state()
    try:
        check('Prepare isolated adventure arena',prepare)
        choices = {'melee':melee,'bow':bow,'damage':damage,'enchant':enchanting,'portal':portals}
        for name in args.checks:
            check(name,choices[name])
    finally:
        if state()['input_captured']:
            press('ESC',shift=True)
            wait_for(lambda s:not s['input_captured'])
        send('settings',values={'camera_view':initial['camera_view']})
    print('PASS all requested adventure checks',flush=True)


if __name__=='__main__':
    main()
