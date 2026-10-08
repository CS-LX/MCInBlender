"""Pack animated atlas tiles into one upload and one GPU draw."""
import struct
import numpy as np
from .protocol import ProtocolError


def pack_patches(patches, atlas_width, atlas_height, max_width=1024):
    decoded = []
    for data in patches:
        if len(data)<16:
            raise ProtocolError('Short atlas patch header')
        x,y,w,h = struct.unpack_from('<IIII',data)
        if not w or not h or x+w>atlas_width or y+h>atlas_height or len(data)!=16+w*h*4:
            raise ProtocolError('Invalid atlas patch')
        decoded.append((x,y,w,h,data[16:]))
    if not decoded:
        return None,[],[]
    width = min(max(max_width,max(p[2] for p in decoded)),sum(p[2] for p in decoded))
    placements = []
    sx = sy = row_height = 0
    for x,y,w,h,pixels in decoded:
        if sx+w>width:
            sx = 0
            sy += row_height
            row_height = 0
        placements.append((sx,sy,x,y,w,h,pixels))
        sx += w
        row_height = max(row_height,h)
    height = sy+row_height
    sheet = np.zeros((height,width,4),dtype=np.uint8)
    positions,uvs = [],[]
    for sx,sy,x,y,w,h,pixels in placements:
        sheet[sy:sy+h,sx:sx+w] = np.frombuffer(pixels,dtype=np.uint8).reshape(h,w,4)
        rectangle = [(2*x/atlas_width-1,2*y/atlas_height-1),(2*(x+w)/atlas_width-1,2*y/atlas_height-1),
                     (2*(x+w)/atlas_width-1,2*(y+h)/atlas_height-1),(2*x/atlas_width-1,2*(y+h)/atlas_height-1)]
        tex = [(sx/width,sy/height),((sx+w)/width,sy/height),((sx+w)/width,(sy+h)/height),(sx/width,(sy+h)/height)]
        positions.extend(rectangle[i] for i in (0,1,2,0,2,3))
        uvs.extend(tex[i] for i in (0,1,2,0,2,3))
    return sheet,positions,uvs
