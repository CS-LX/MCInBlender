"""Isolated real JVM exercise of host replacement and render-ring back pressure."""
import json, os, shutil, struct, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from blender_minecraft.transport import HostLink
from blender_minecraft import protocol as P
from launch import discover

OUT = ROOT / 'artifacts' / 'host-reconnect' / time.strftime('%Y%m%d-%H%M%S')
OUT.mkdir(parents=True)
GAME = OUT / 'game'
GAME.mkdir()
source = ROOT / 'minecraft/run'
shutil.copytree(source / 'saves/MCInBlender Survival', GAME / 'saves/MCInBlender Survival',
                ignore=shutil.ignore_patterns('session.lock'))
shutil.copy2(source / 'options.txt', GAME / 'options.txt')
_, java = discover()
name = 'Local\\MCInBlender_Reconnect_' + str(os.getpid())
args = [str(Path(java) / 'bin/java.exe'), '-Xms512m', '-Xmx4096m',
        '@' + str(ROOT / 'minecraft/build/loom-cache/argFiles/runClient'),
        '-Dfabric.dli.config=' + str(ROOT / 'minecraft/.gradle/loom-cache/launch.cfg'),
        '-Dfabric.dli.env=client', '-Dfabric.dli.main=net.fabricmc.loader.impl.launch.knot.KnotClient',
        '--enable-native-access=ALL-UNNAMED', '-XX:StackShadowPages=32',
        '--sun-misc-unsafe-memory-access=allow', '-Dskycraft.link=' + name,
        '-Dskycraft.startHidden=true', '-Dskycraft.quitWithSkyrim=true',
        '-Dmciblender.host=true', '-Dmciblender.vanilla=true',
        '-Dmciblender.worldName=MCInBlender Survival',
        'net.fabricmc.devlaunchinjector.Main', '--username', 'ReconnectTest', '--gameDir', str(GAME)]
link = HostLink(name)
log = (OUT / 'minecraft.log').open('w')
game = subprocess.Popen(args, cwd=GAME, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW)
report = {'minecraft_pid': game.pid, 'phases': []}
viewport = (640, 360)
print(json.dumps({'output': str(OUT), 'pid': game.pid}), flush=True)


def pump(flags=1, drain=True):
    assert game.poll() is None, 'Minecraft exited unexpectedly'
    link.state(position=(0, 204, 42), width=viewport[0], height=viewport[1], teleport=0, flags=flags)
    link.heartbeat()
    messages = list(link.render_messages(budget_ms=8)) if drain else []
    link.overlay()
    time.sleep(.016)
    return messages


def snapshot(label, timeout=90):
    started = time.monotonic()
    counts, assets, atmosphere, window_hidden = {}, set(), False, False
    while time.monotonic() - started < timeout:
        for kind, data in pump():
            if kind == 3:
                # Mirror the receiver: environment records sent before CLEAR
                # cannot satisfy the new snapshot, even in this same drain.
                counts, assets, atmosphere = {}, set(), False
            counts[kind] = counts.get(kind, 0) + 1
            if kind == 14:
                assets.add(struct.unpack_from('<I', data)[0])
            if kind == 12:
                environment = json.loads(data)
                atmosphere |= bool(environment.get('atmosphere'))
                window_hidden = environment.get('windowHidden', False)
        ack = link.atomic_load64(P.CLIENT_GENERATION)
        if (link.alive and ack == link.generation and counts.get(1) and counts.get(2)
                and counts.get(3) and assets.issuperset({0, 1, 2, 3, 4}) and atmosphere and window_hidden):
            actual_pid = struct.unpack_from('<I', link.m, 0x0c)[0]
            assert actual_pid == game.pid, (actual_pid, game.pid)
            phase = {'phase': label, 'seconds': round(time.monotonic()-started, 3),
                     'nonce': ack, 'records': counts, 'assets': sorted(assets), 'atmosphere': atmosphere,
                     'window_hidden': window_hidden, 'viewport': viewport}
            report['phases'].append(phase)
            print(json.dumps(phase), flush=True)
            return
    raise AssertionError(f'{label} missing snapshot: records={counts} assets={assets} alive={link.alive}')


try:
    snapshot('initial')
    first_nonce = link.generation
    link.close()
    link = HostLink(name)
    viewport = (960, 540)
    assert link.generation != first_nonce
    snapshot('rapid_restart_same_process')
    link.close()
    time.sleep(1.2)
    link = HostLink(name)
    snapshot('restart_after_offline')
    link.close()
    link = HostLink(name)
    # Reserve the entire ring before the new nonce is announced by heartbeat.
    # There are deliberately no readable records; only free it after verifying
    # that the actual JVM keeps updating its HUD/state while mandatory sends fail.
    full = P.RENDER_BYTES - 0x80
    link.store64(P.RENDER, full)
    start = time.monotonic()
    frames = []
    while time.monotonic() - start < 2:
        pump(drain=False)
        player = link.player()
        if player:
            frames.append(player.frame)
    assert link.alive and frames and frames[-1] > frames[0] + 10, frames
    report['backpressure_frame_advance'] = frames[-1] - frames[0]
    link.store64(P.RENDER + 0x40, full)
    snapshot('full_ring_retry')
    for _ in range(30):
        pump(flags=1 | P.NO_WORLD_EXPORT)
    snapshot('world_visibility_resume')
    report['ok'] = True
finally:
    if game.poll() is None:
        link.input(9)
        deadline = time.monotonic() + 20
        while game.poll() is None and time.monotonic() < deadline:
            try:
                pump()
            except AssertionError:
                break
        if game.poll() is None:
            game.terminate()
            game.wait(timeout=10)
    link.close()
    report['minecraft_exit'] = game.returncode
    (OUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
