"""Regression: restarting the Blender host must not teleport a vanilla player."""
import json
import math
import subprocess
import sys
import time
from verify_runtime import ROOT, send, state, wait_for
from verify_survival import command

command('gamemode spectator',lambda s:s['environment'].get('gameMode')=='spectator')
command('tp @s -29.5 90 -6.5')
before = wait_for(lambda s:math.dist(s['position'],(-29.5,90,-6.5))<0.1)
old_pid = before.get('host_pid')
send('shutdown')
time.sleep(3)
subprocess.run([sys.executable,str(ROOT/'scripts'/'launch.py'),'--only','blender','--world','normal','--test-input'],check=True)
after = wait_for(lambda s:s.get('host_pid')!=old_pid and s['alive'] and s['sections']>0 and s['player']['flags']&1,60)
time.sleep(3)
after = state()
assert math.dist(before['position'],after['position'])<0.1,(before['position'],after['position'])
assert not after['errors'],after['errors']
result = {'passed':True,'before':before['position'],'after':after['position'],'new_host_pid':after['host_pid']}
(ROOT/'artifacts'/'reconnect-test.json').write_text(json.dumps(result,indent=2))
print('PASS host reconnect preserves position',result)
