"""Queue one JSON action for the Blender session's diagnostic interface."""
import json
from pathlib import Path
import sys
import time
import uuid

root = Path(__file__).resolve().parents[1]/'.local'/'control'
root.mkdir(parents=True,exist_ok=True)
data = json.loads(sys.argv[1])
target = root/(f'{time.monotonic_ns():020d}-{uuid.uuid4().hex}.json')
temp = target.with_suffix('.tmp')
temp.write_text(json.dumps(data),encoding='utf8')
temp.rename(target)
