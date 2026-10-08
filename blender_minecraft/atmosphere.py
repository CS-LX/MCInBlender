"""Blender GPU presentation of Minecraft's atmosphere and precipitation columns."""
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector


class AtmosphereRenderer:
    def __init__(self):
        interface = gpu.types.GPUStageInterfaceInfo('mciblender_sky_varyings')
        interface.smooth('VEC2','screenUV')
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0,'VEC2','position')
        info.vertex_out(interface)
        for kind,name in [('MAT4','inverseVP'),('VEC4','eye'),('VEC3','skyColor'),('VEC3','horizonColor'),
                          ('VEC4','celestial')]:
            info.push_constant(kind,name)
        for index,name in enumerate(('sun','moon','endSky')):
            info.sampler(index,'FLOAT_2D',name)
        info.fragment_out(0,'VEC4','fragColor')
        info.vertex_source('void main(){screenUV=position;gl_Position=vec4(position,1.0,1.0);}')
        info.fragment_source('''
            vec3 disc(vec3 ray, float angle, float size, sampler2D image){
                vec3 direction=vec3(-sin(angle),0.0,cos(angle));
                vec3 right=vec3(0.0,1.0,0.0), up=cross(direction,right);
                float facing=dot(ray,direction);
                if(facing<=0.0) return vec3(0.0);
                vec2 uv=vec2(dot(ray,right),-dot(ray,up))/(facing*size)*0.5+0.5;
                if(any(lessThan(uv,vec2(0.0)))||any(greaterThan(uv,vec2(1.0)))) return vec3(0.0);
                vec4 color=texture(image,uv);
                return color.rgb*color.a;
            }
            void main(){
                vec4 farPoint=inverseVP*vec4(screenUV,1.0,1.0);
                vec3 ray=normalize(farPoint.xyz/farPoint.w-eye.xyz);
                if(eye.w<0.5) ray=normalize((inverseVP*vec4(0.0,0.0,1.0,0.0)).xyz);
                vec3 color=mix(horizonColor,skyColor,smoothstep(-0.12,0.45,ray.z));
                if(celestial.w>=0.0){
                    color+=disc(ray,celestial.x,0.3,sun)*celestial.w;
                    color+=disc(ray,celestial.y,0.2,moon)*celestial.w;
                    vec3 cell=floor(ray*400.0);
                    float seed=fract(sin(dot(cell,vec3(12.9898,78.233,39.425)))*43758.5453);
                    float point=pow(max(0.0,1.0-length(fract(ray*400.0)-0.5)*2.0),5.0);
                    color+=vec3(step(0.995,seed)*point*celestial.z*smoothstep(0.0,0.2,ray.z));
                } else if(celestial.w<-1.5){
                    color=texture(endSky,fract(vec2(atan(ray.y,ray.x),asin(ray.z))*4.0)).rgb*0.18;
                }
                fragColor=vec4(color,1.0);
            }
        ''')
        self.sky = gpu.shader.create_from_info(info)
        self.sky_batch = batch_for_shader(self.sky,'TRI_FAN',{'position':[(-1,-1),(1,-1),(1,1),(-1,1)]})
        interface = gpu.types.GPUStageInterfaceInfo('mciblender_weather_varyings')
        interface.smooth('VEC2','texCoord')
        interface.smooth('VEC4','tint')
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4','transform')
        info.vertex_in(0,'VEC3','position')
        info.vertex_in(1,'VEC2','uv')
        info.vertex_in(2,'VEC4','color')
        info.vertex_in(3,'VEC2','lightLevels')
        info.vertex_out(interface)
        info.sampler(0,'FLOAT_2D','image')
        info.sampler(1,'FLOAT_2D','lightmap')
        info.fragment_out(0,'VEC4','fragColor')
        info.vertex_source('''void main(){gl_Position=transform*vec4(position,1.0);texCoord=uv;
            tint=color*vec4(texelFetch(lightmap,clamp(ivec2(lightLevels),ivec2(0),ivec2(15)),0).rgb,1.0);}''')
        info.fragment_source('void main(){fragColor=texture(image,fract(texCoord))*tint;if(fragColor.a<0.01)discard;}')
        self.weather = gpu.shader.create_from_info(info)

    def draw_sky(self, context, state, textures):
        if not all(k in textures for k in (0,1,4)):
            return
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('NONE')
        view = context.region_data
        inverse_view = view.view_matrix.inverted()
        skybox = state.get('skybox','NONE')
        brightness = state.get('rainBrightness',1) if skybox=='OVERWORLD' else (-2 if skybox=='END' else -1)
        self.sky.bind()
        self.sky.uniform_float('inverseVP',view.perspective_matrix.inverted())
        self.sky.uniform_float('eye',(*inverse_view.translation,1 if view.is_perspective else 0))
        self.sky.uniform_float('skyColor',state.get('skyColor',(0,0,0)))
        self.sky.uniform_float('horizonColor',state.get('fogColor',(0,0,0)))
        self.sky.uniform_float('celestial',(state.get('sunAngle',0),state.get('moonAngle',0),
                                           state.get('stars',0),brightness))
        for name,index in [('sun',0),('moon',1),('endSky',4)]:
            self.sky.uniform_sampler(name,textures[index])
        self.sky_batch.draw(self.sky)

    def draw_weather(self, context, state, textures, lightmap):
        intensity = state.get('rain',0)
        if intensity<=0:
            return
        eye = context.region_data.view_matrix.inverted().translation
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.blend_set('ALPHA')
        self.weather.bind()
        self.weather.uniform_float('transform',context.region_data.perspective_matrix)
        self.weather.uniform_sampler('lightmap',lightmap)
        for key,texture_id in [('rainColumns',2),('snowColumns',3)]:
            if texture_id not in textures:
                continue
            positions,uvs,colors,lights = [],[],[],[]
            for x,z,bottom,top,u,v,packed in state.get(key,[]):
                center = Vector((x+0.5,-z-0.5,0))
                toward = Vector((eye.x-center.x,eye.y-center.y,0))
                distance = toward.length
                side = Vector((-toward.y,toward.x,0)).normalized()*0.5 if distance>0.001 else Vector((0.5,0,0))
                lo,hi = center-side,center+side
                rectangle = [(lo.x,lo.y,bottom),(hi.x,hi.y,bottom),(hi.x,hi.y,top),(lo.x,lo.y,top)]
                uv = [(u,bottom/4+v),(u+1,bottom/4+v),(u+1,top/4+v),(u,top/4+v)]
                alpha = intensity*max(0.15,1-distance/24)*0.65
                for i in (0,1,2,0,2,3):
                    positions.append(rectangle[i]); uvs.append(uv[i])
                    colors.append((1,1,1,alpha)); lights.append(((packed>>4)&15,(packed>>20)&15))
            if positions:
                batch = batch_for_shader(self.weather,'TRIS',{'position':positions,'uv':uvs,'color':colors,'lightLevels':lights})
                self.weather.uniform_sampler('image',textures[texture_id])
                batch.draw(self.weather)
