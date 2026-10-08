"""Keep installed add-on data out of Blender's installation and scripts folders."""
import json
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def build_info():
    path = PACKAGE/'build-info.json'
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else {
        'version': '0.1.0.0', 'channel': 'source', 'sha': 'working-tree'}


def data_root():
    override = os.environ.get('MCIBLENDER_DATA_DIR')
    if override:
        root = Path(override).expanduser().resolve()
    elif (PACKAGE/'build-info.json').exists():
        import bpy
        root = Path(bpy.utils.user_resource('CONFIG', path='mciblender', create=True))
    else:
        root = PACKAGE.parent
    root.mkdir(parents=True, exist_ok=True)
    return root


def controls_enabled():
    return not (PACKAGE/'build-info.json').exists() or os.environ.get('MCIBLENDER_TEST_CONTROL') == '1'
