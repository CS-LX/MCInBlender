"""Build the three-function Windows atomic helper from source (GCC or MSVC)."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def build():
    output = ROOT/'.local'/'native'
    output.mkdir(parents=True,exist_ok=True)
    target = output/'mc_atomic.dll'
    source = ROOT/'native'/'atomic.c'
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return target
    gcc = shutil.which('gcc')
    if gcc:
        subprocess.run([gcc,'-shared','-O2','-static-libgcc',str(source),'-o',str(target)],check=True)
    else:
        vswhere = Path('C:/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe')
        install = subprocess.check_output([str(vswhere),'-latest','-products','*','-requires',
            'Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
        vcvars = Path(install)/'VC'/'Auxiliary'/'Build'/'vcvars64.bat'
        # Paths are data supplied by the local VS installer. A batch file is required to retain
        # the compiler environment for the subsequent cl invocation.
        script = output/'build.cmd'
        script.write_text(f'@echo off\ncall "{vcvars}"\nif errorlevel 1 exit /b 1\ncl /nologo /LD /O2 "{source}" /link /OUT:"{target}"\n')
        subprocess.run(['cmd','/d','/c',str(script)],cwd=output,check=True)
    return target


if __name__ == '__main__':
    print(build())
