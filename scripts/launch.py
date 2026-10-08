"""Launch an isolated developer session. Local runtimes and logs are never published."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import ctypes

ROOT = Path(__file__).resolve().parents[1]


def discover(require_blender=True, require_java=True):
    config_file = ROOT/'.local'/'config.json'
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    blender = config.get('blender') or shutil.which('blender') or next((str(p) for p in [
        Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Steam/steamapps/common/Blender/blender.exe',
        *Path('C:/Program Files/Blender Foundation').glob('Blender */blender.exe')] if p.exists()),None)
    java = config.get('java_home') or next((str(p.parent.parent) for p in
        Path(os.environ.get('LOCALAPPDATA','')).glob('Packages/Microsoft.*/LocalCache/Local/runtime/java-runtime-epsilon/windows-x64/java-runtime-epsilon/bin/javac.exe')),None)
    if not java:
        java = os.environ.get('JAVA_HOME')
    if (require_blender and not blender) or (require_java and not java):
        raise SystemExit('Set blender and java_home in .local/config.json (requires Blender 5+ and JDK 25)')
    return blender,java


def running(suffix):
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenMutexW.argtypes = [ctypes.c_uint32,ctypes.c_int,ctypes.c_wchar_p]
    kernel.OpenMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenMutexW(0x00100000,False,'Local\\MCInBlender_SkyCraft_v11'+suffix)
    if handle:
        kernel.CloseHandle(handle)
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only',choices=['blender','minecraft','build'])
    ap.add_argument('--test-input',action='store_true',help='Enable Blender event simulation for integration tests')
    ap.add_argument('--keep-minecraft',action='store_true',help='Developer mode: keep Minecraft alive when Blender closes, for host reconnect tests')
    ap.add_argument('--verification',choices=['fusion','performance','lifecycle','lighting'],help='Run Blender integration checks in an isolated instance')
    ap.add_argument('--world',choices=['scene','normal'],default='scene')
    ap.add_argument('--blend',type=Path,help='Use models from this .blend file as the host scene')
    args = ap.parse_args()
    if args.blend and (not args.blend.is_file() or args.blend.suffix.lower()!='.blend'):
        ap.error('--blend must name an existing .blend file')
    if os.name != 'nt':
        raise SystemExit('The current shared-memory bridge requires Windows x64.')
    if args.only in (None,'blender') and running('_blender_owner'):
        raise SystemExit('A Blender host is already running. Close or stop it before starting another.')
    if args.only in (None,'minecraft') and running('_minecraft'):
        raise SystemExit('The Minecraft bridge is already running. Use --only blender to reconnect its host.')
    from build_native import build
    build()
    blender,java = discover(args.only in (None,'blender'),args.only in (None,'minecraft','build'))
    logs = ROOT/'logs'
    logs.mkdir(exist_ok=True)
    local = ROOT/'.local'
    local.mkdir(exist_ok=True)
    process_file = local/'processes.json'
    processes = json.loads(process_file.read_text()) if process_file.exists() else {}
    if args.only in (None,'blender'):
        script = ROOT/'scripts'/(f'verify_{args.verification}_in_blender.py' if args.verification else 'bootstrap_blender.py')
        out = open(logs/'blender.log','w',encoding='utf8')
        env = os.environ.copy()
        env['MCIBLENDER_WORLD'] = args.world
        if args.blend:
            env['MCIBLENDER_USE_CURRENT_SCENE'] = '1'
        temp = ROOT/'.local'/'blender-temp'
        temp.mkdir(parents=True,exist_ok=True)
        env['TEMP'] = env['TMP'] = str(temp)
        command = [blender,'--factory-startup']
        if args.blend:
            command.append(str(args.blend.resolve()))
        if args.test_input:
            command.append('--enable-event-simulate')
        command.extend(['--python',str(script)])
        proc = subprocess.Popen(command,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT)
        processes['blender'] = proc.pid
    if args.only in (None,'minecraft','build'):
        env = os.environ.copy()
        env['JAVA_HOME'] = java
        env['MCIBLENDER_KEEP_MINECRAFT'] = '1' if args.keep_minecraft else '0'
        env['GRADLE_USER_HOME'] = str(ROOT/'.cache'/'gradle')
        env['MCIBLENDER_WORLD'] = args.world
        task = 'build' if args.only == 'build' else 'runClient'
        out = open(logs/('build.log' if task == 'build' else 'minecraft-build.log'),'w',encoding='utf8')
        proc = subprocess.Popen(['cmd.exe','/d','/c','gradlew.bat',task,'--console=plain'],cwd=ROOT/'minecraft',env=env,
                                stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        processes['build' if task == 'build' else 'gradle'] = proc.pid
    process_file.write_text(json.dumps(processes,indent=2))
    print(json.dumps(processes))
    if args.only == 'build':
        code = proc.wait()
        print(f'Build exited {code}; see {logs / "build.log"}')
        return code


if __name__ == '__main__':
    raise SystemExit(main())
