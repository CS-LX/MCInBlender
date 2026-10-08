"""Conservative world-space AABB/frustum rejection, independent of Blender."""
import numpy as np


def visible_bounds(centers, half_sizes, view_projection):
    centers = np.asarray(centers,dtype=np.float32).reshape(-1,3)
    if not len(centers):
        return np.zeros(0,dtype=bool)
    half_sizes = np.asarray(half_sizes,dtype=np.float32).reshape(-1,3)
    m = np.asarray(view_projection,dtype=np.float32).reshape(4,4)
    planes = np.stack([m[3]+m[i]*sign for i in range(3) for sign in (1,-1)])
    distance = centers @ planes[:,:3].T + planes[:,3]
    radius = half_sizes @ np.abs(planes[:,:3]).T
    return np.all(distance+radius>=-0.001,axis=1)
