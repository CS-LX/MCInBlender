"""Bounded light selection from SkyCraft records, without Blender dependencies."""
import math
import struct
import numpy as np
from .protocol import ProtocolError

LIGHT_DTYPE = np.dtype([('xyz','u1',3),('level','u1'),('color','<u4')])


def nearest_lights(records, bounds, focus, limit=32):
    """Select emitters whose light radius reaches a model AABB (Minecraft axes)."""
    if not bounds or limit<=0:
        return []
    lows = np.asarray([b[0] for b in bounds],dtype=np.float64)
    highs = np.asarray([b[1] for b in bounds],dtype=np.float64)
    candidates = []
    focus = np.asarray(focus,dtype=np.float64)
    for key,payload in records.items():
        origin = np.asarray(key,dtype=np.float64)*16
        gap = np.maximum(np.maximum(lows-(origin+16),origin-highs),0)
        if np.min(np.sum(gap*gap,axis=1))>18**2:
            continue
        if len(payload)<16:
            raise ProtocolError('Short light header')
        sx,sy,sz,count = struct.unpack_from('<iiiI',payload)
        if (sx,sy,sz)!=tuple(key) or count>4096 or len(payload)!=16+count*8:
            raise ProtocolError('Invalid light record')
        values = np.frombuffer(payload,offset=16,dtype=LIGHT_DTYPE)
        if np.any(values['xyz']>15) or np.any(values['level']>15):
            raise ProtocolError('Invalid light coordinates or level')
        centers = values['xyz'].astype(np.float64)+origin+0.5
        distances = np.full(count,np.inf)
        for low,high in zip(lows,highs):
            delta = np.maximum(np.maximum(low-centers,centers-high),0)
            distances = np.minimum(distances,np.sum(delta*delta,axis=1))
        valid = np.flatnonzero((values['level']>0)&(distances<=(values['level']+1.0)**2))
        for index in valid:
            center = centers[index]
            packed = int(values['color'][index])
            candidates.append({'key':tuple(int(v) for v in center-0.5),
                               'position':tuple(center),'level':int(values['level'][index]),
                               'color':tuple(((packed>>(8*i))&255)/255 for i in range(3)),
                               'kind':(packed>>24)&15,
                               'score':float(distances[index])+0.02*float(np.sum((center-focus)**2))})
    candidates.sort(key=lambda light:(light['score'],light['key']))
    return candidates[:limit]


def sky_lighting(atmosphere, lightmap, strength=1):
    """Artist-adjustable physical-light approximation to vanilla's display palette."""
    samples = lightmap or {'sky':[255,255,255,255],'dark':[24,24,24,255]}
    skybox = atmosphere.get('skybox','NONE')
    sample = samples['sky'] if skybox=='OVERWORLD' else samples['dark']
    rgb = [max(0,min(1,c/255))**2.2 for c in sample[:3]]
    peak = max(max(rgb),0.0001)
    color = tuple(c/peak for c in rgb)
    sun,moon = atmosphere.get('sunAngle',0),atmosphere.get('moonAngle',math.pi)
    above = lambda angle:max(0,min(1,math.cos(angle)*8))
    energy = peak*2.4*strength
    return {'color':color,'sun':energy*above(sun) if skybox=='OVERWORLD' else 0,
            'moon':energy*above(moon) if skybox=='OVERWORLD' else 0,
            'fill':peak*(0.3 if skybox=='OVERWORLD' else 1.5)*strength,
            'sun_direction':(-math.sin(sun),0,math.cos(sun)),
            'moon_direction':(-math.sin(moon),0,math.cos(moon))}
