"""Real survival interactions through Blender's mouse/keyboard, in the dev save.

Commands only prepare a deterministic arena/materials and read server state.
Crafting, moving stacks, opening containers, smelting and using blocks/items are
performed by the actual Blender modal operator. No menu-click packets are forged.
"""
import json
import math
import time
from verify_runtime import ROOT, send, state, wait_for
from verify_survival import command, event, press

RESULTS = []
HOTBAR = ['ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE']


def env():
    return state()['environment']


def check(name, function):
    try:
        result = function()
        RESULTS.append({'name':name,'passed':True,'evidence':result})
        print('PASS',name,result,flush=True)
    except Exception as exc:
        RESULTS.append({'name':name,'passed':False,'error':str(exc)})
        print('FAIL',name,exc,flush=True)
        raise
    finally:
        (ROOT/'artifacts').mkdir(exist_ok=True)
        (ROOT/'artifacts'/'gameplay-tests.json').write_text(json.dumps(RESULTS,indent=2))


def wait_env(predicate, timeout=15):
    return wait_for(lambda s:predicate(s['environment']),timeout)['environment']


def slot(index):
    return next(s for s in env()['menuSlots'] if s['index']==index)


def item_slot(item, minimum=0):
    return next(s['index'] for s in env()['menuSlots'] if s['item']=='minecraft:'+item and s['count'] and s['index']>=minimum)


def click_slot(index, button='LEFTMOUSE', shift=False):
    current = state()
    e = current['environment']
    cell = next(s for s in e['menuSlots'] if s['index']==index)
    rx,ry,rw,rh = current['viewport_region']
    x = round(rx+(e['menuLeft']+cell['x']+8)/e['guiWidth']*rw)
    y = round(ry+(1-(e['menuTop']+cell['y']+8)/e['guiHeight'])*rh)
    event('MOUSEMOVE','NOTHING',x=x,y=y)
    if shift:
        event('LEFT_SHIFT')
    time.sleep(0.2)
    press(button,x=x,y=y)
    if shift:
        event('LEFT_SHIFT','RELEASE')


def close_screen():
    press('ESC')
    wait_env(lambda e:e['screen']=='')


def look_at(target, block=None):
    p = state()['player']['eye']
    dx,dy,dz = [target[a]-p[a] for a in range(3)]
    yaw = math.degrees(math.atan2(-dx,dz))
    pitch = -math.degrees(math.atan2(dy,math.hypot(dx,dz)))
    send('look',yaw=yaw,pitch=pitch)
    if block:
        wait_env(lambda e:all(e.get('targetBlock',{}).get(a)==v for a,v in zip(('x','y','z'),block)))
    else:
        wait_for(lambda s:abs(s['yaw']-yaw)<0.01 and abs(s['pitch']-pitch)<0.01)


def open_block(block, screen):
    look_at(tuple(c+0.5 for c in block),block)
    press('RIGHTMOUSE')
    return wait_env(lambda e:e['screen']==screen)


def select_item(item):
    press('E')
    wait_env(lambda e:e['screen']=='InventoryScreen')
    index = item_slot(item,36)
    close_screen()
    press(HOTBAR[index-36])
    wait_env(lambda e:e['heldItem']=='minecraft:'+item)


def assert_block(position, block, label):
    marker = 'MCIBLENDER_CHECK_'+label
    response = command(f'execute if block {position[0]} {position[1]} {position[2]} {block} run say {marker}')
    assert marker in response,response
    return response


def prepare():
    wait_for(lambda s:s['alive'] and s['environment'].get('vanilla') and 'inventory' in s['environment'],60)
    command('difficulty peaceful')
    command('time set day')
    command('gamemode creative')
    command('fill -6 99 -6 20 99 20 minecraft:stone')
    command('fill -6 100 -6 20 110 20 minecraft:air')
    command('tp @s 0.5 100 0.5',lambda s:math.dist(s['position'],(0.5,100,0.5))<0.1)
    # Clear only this isolated development character's test inventory.
    command('clear')
    command('gamemode survival',lambda s:s['environment'].get('gameMode')=='survival')
    command('give @s minecraft:oak_log 1',lambda s:s['environment'].get('inventory',{}).get('minecraft:oak_log')==1)
    send('capture_input')
    wait_for(lambda s:s['input_captured'])
    return {'arena_floor_y':99,'game_mode':'survival','materials':{'oak_log':1}}


def crafting():
    press('E')
    wait_env(lambda e:e['screen']=='InventoryScreen')
    click_slot(item_slot('oak_log',9))
    wait_env(lambda e:e['carried']['item']=='minecraft:oak_log')
    click_slot(1)
    wait_env(lambda e:any(s['index']==0 and s['item']=='minecraft:oak_planks' and s['count']==4 for s in e['menuSlots']))
    click_slot(0,shift=True)
    wait_env(lambda e:e['inventory'].get('minecraft:oak_planks')==4)
    click_slot(item_slot('oak_planks',9))
    wait_env(lambda e:e['carried']['count']==4)
    for index in (1,2,3,4):
        click_slot(index,'RIGHTMOUSE')
        wait_env(lambda e:any(s['index']==index and s['item']=='minecraft:oak_planks' for s in e['menuSlots']))
    wait_env(lambda e:any(s['index']==0 and s['item']=='minecraft:crafting_table' for s in e['menuSlots']))
    send('capture_window',name='crafting-table-recipe-in-blender')
    click_slot(0,shift=True)
    result = wait_env(lambda e:e['inventory'].get('minecraft:crafting_table')==1)
    close_screen()
    select_item('crafting_table')
    look_at((0.5,100,3.5),(0,99,3))
    press('RIGHTMOUSE')
    wait_env(lambda e:not e['inventory'].get('minecraft:crafting_table'))
    assert_block((0,100,3),'minecraft:crafting_table','CRAFTED_TABLE_PLACED')
    command('give @s minecraft:oak_planks 2')
    open_block((0,100,3),'CraftingScreen')
    click_slot(item_slot('oak_planks',10))
    wait_env(lambda e:e['carried']['count']==2)
    click_slot(1,'RIGHTMOUSE')
    wait_env(lambda e:e['carried']['count']==1)
    click_slot(4)
    wait_env(lambda e:any(s['index']==0 and s['item']=='minecraft:stick' and s['count']==4 for s in e['menuSlots']))
    click_slot(0,shift=True)
    final = wait_env(lambda e:e['inventory'].get('minecraft:stick')==4)
    close_screen()
    return {'oak_log':1,'crafted_planks':4,'crafted_and_placed_tables':1,'crafted_sticks':final['inventory']['minecraft:stick']}


def chest():
    command('setblock 2 100 3 minecraft:chest[facing=north]')
    command('give @s minecraft:apple 5')
    open_block((2,100,3),'ContainerScreen')
    click_slot(item_slot('apple',27),shift=True)
    wait_env(lambda e:any(s['index']==0 and s['item']=='minecraft:apple' and s['count']==5 for s in e['menuSlots']))
    close_screen()
    reopened = open_block((2,100,3),'ContainerScreen')
    assert reopened['menuSlots'][0]['count']==5,reopened['menuSlots'][0]
    send('capture_window',name='chest-storage-in-blender')
    click_slot(0,shift=True)
    wait_env(lambda e:e['inventory'].get('minecraft:apple')==5)
    close_screen()
    return {'deposited':5,'persisted_after_reopen':5,'withdrawn':5}


def furnace():
    command('setblock -2 100 3 minecraft:furnace[facing=north]')
    command('give @s minecraft:raw_iron 1')
    command('give @s minecraft:coal 1')
    open_block((-2,100,3),'FurnaceScreen')
    click_slot(item_slot('raw_iron',3),shift=True)
    wait_env(lambda e:any(s['index']==0 and s['item']=='minecraft:raw_iron' for s in e['menuSlots']))
    click_slot(item_slot('coal',3),shift=True)
    wait_env(lambda e:any(s['index']==2 and s['item']=='minecraft:iron_ingot' and s['count']==1 for s in e['menuSlots']),30)
    send('capture_window',name='furnace-smelting-in-blender')
    click_slot(2,shift=True)
    result = wait_env(lambda e:e['inventory'].get('minecraft:iron_ingot')==1)
    close_screen()
    return {'input':'raw_iron','fuel':'coal','collected_iron_ingots':result['inventory']['minecraft:iron_ingot']}


def redstone():
    command('setblock 5 100 3 minecraft:redstone_lamp')
    command('setblock 5 100 2 minecraft:lever[face=floor,facing=north,powered=false]')
    command('tp @s 5.5 100 -0.5',lambda s:math.dist(s['position'],(5.5,100,-0.5))<0.1)
    look_at((5.5,100.15,2.5),(5,100,2))
    assert_block((5,100,3),'minecraft:redstone_lamp[lit=false]','LAMP_OFF')
    press('RIGHTMOUSE')
    wait_env(lambda e:'powered=true' in e.get('targetBlock',{}).get('state',''))
    on = assert_block((5,100,3),'minecraft:redstone_lamp[lit=true]','LAMP_ON')
    send('capture_window',name='redstone-lamp-in-blender')
    press('RIGHTMOUSE')
    wait_env(lambda e:'powered=false' in e.get('targetBlock',{}).get('state',''))
    assert_block((5,100,3),'minecraft:redstone_lamp[lit=false]','LAMP_OFF_AGAIN')
    return {'lever_mouse_interaction':True,'lamp_lit_sequence':[False,True,False]}


def water():
    command('give @s minecraft:water_bucket 1')
    command('tp @s 10.5 100 0.5',lambda s:math.dist(s['position'],(10.5,100,0.5))<0.1)
    select_item('water_bucket')
    look_at((10.5,100,3.5),(10,99,3))
    before = state()['render_messages']['2']
    press('RIGHTMOUSE')
    wait_env(lambda e:e['inventory'].get('minecraft:bucket')==1)
    assert_block((10,100,3),'minecraft:water[level=0]','WATER_SOURCE')
    assert_block((11,100,3),'minecraft:water','WATER_SPREAD')
    send('capture_window',name='water-flow-in-blender')
    after = state()['render_messages']['2']
    assert after>before,(before,after)
    return {'bucket_used':True,'source_verified':True,'neighbor_flow_verified':True,'mesh_updates':after-before}


if __name__ == '__main__':
    try:
        check('Prepare isolated survival interaction arena',prepare)
        check('2x2 and 3x3 crafting, place and use crafted table',crafting)
        check('Chest deposit, persistence and withdrawal',chest)
        check('Fuel furnace, smelt and collect iron',furnace)
        check('Toggle redstone lamp with lever',redstone)
        check('Place bucket water and observe vanilla flow',water)
    finally:
        press('ESC',shift=True)
