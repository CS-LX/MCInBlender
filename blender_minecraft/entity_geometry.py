"""SkyCraft lightweight item, projectile and crack meshes.

Geometry follows SkyCraft WorldRender.cpp (chasmlol, MIT; see third-party notices).
"""
import math
import struct
import numpy as np
from .protocol import mc_to_blender


def build(records):
    positions,uvs,colors = [],[],[]
    solid_count = 0

    def quad(points, rect, color=(1,1,1,1)):
        u0,v0,u1,v1 = rect
        tex = [(u0,v0),(u1,v0),(u1,v1),(u0,v1)]
        for i in (0,1,2,0,2,3):
            positions.append(mc_to_blender(points[i]))
            uvs.append(tex[i])
            colors.append(color)

    for cracks in (False,True):
        for raw in records:
            kind,ident,*data = struct.unpack('<II21fI',raw)
            if kind == 6 or (kind == 5) != cracks:
                continue
            x,y,z,yaw,pitch,scale = data[:6]
            ext = data[6:9]
            rects = [data[9+i*4:13+i*4] for i in range(3)]
            tint = data[-1]
            p = np.array((x,y,z))
            spin = math.radians(yaw)
            if kind in (4,5):
                lo = p-np.array((scale,)*3)/2 if kind == 4 else p
                size = np.array((scale,)*3 if kind == 4 else ext)
                points = [lo+size*np.array((i&1,(i>>1)&1,(i>>2)&1)) for i in range(8)]
                center = lo+size/2
                for point in points:
                    dx,dz = point[0]-center[0],point[2]-center[2]
                    point[0] = center[0]+dx*math.cos(spin)-dz*math.sin(spin)
                    point[2] = center[2]+dx*math.sin(spin)+dz*math.cos(spin)
                faces = [(0,1,3,2),(5,4,6,7),(4,0,2,6),(1,5,7,3),(2,3,7,6),(4,5,1,0)]
                for i,indices in enumerate(faces):
                    rect = rects[0 if kind == 5 or i<4 else i-3]
                    color = tuple(((tint >> (a*8))&255)/255 for a in range(4)) if tint and i==4 else (1,1,1,1)
                    quad([points[j] for j in indices],rect,color)
            elif kind == 2:
                half = scale/2
                r = np.array((math.cos(spin)*half,0,math.sin(spin)*half))
                up = np.array((0,half,0))
                quad([p-r+up,p+r+up,p+r-up,p-r-up],rects[0])
            elif kind in (1,3):
                pitch = math.radians(pitch)
                direction = np.array((math.sin(spin)*math.cos(pitch),math.sin(pitch),math.cos(spin)*math.cos(pitch)))
                side = np.array((direction[2],0,-direction[0]))
                length = np.linalg.norm(side)
                side = side/length if length>0.001 else np.array((1,0,0))
                up = np.cross(side,direction)
                fins = [(up+side)*math.sqrt(0.5),(up-side)*math.sqrt(0.5)]
                if kind == 1:
                    unit = 0.9/16
                    for q in fins:
                        quad([p+direction*(-12*unit)-q*2*unit,p+direction*4*unit-q*2*unit,
                              p+direction*4*unit+q*2*unit,p+direction*(-12*unit)+q*2*unit],rects[0])
                    base = p-direction*11*unit
                    a,b = fins[0]*2*unit,fins[1]*2*unit
                    quad([base-a-b,base+a-b,base+a+b,base-a+b],rects[1])
                else:
                    for q in fins:
                        quad([p+q*0.9,p+direction*0.9,p-q*0.9,p-direction*0.9],rects[0])
        if not cracks:
            solid_count = len(positions)
    return np.asarray(positions,dtype=np.float32),np.asarray(uvs,dtype=np.float32),np.asarray(colors,dtype=np.float32),solid_count
