"""Prepara o ambiente privado e abre o banco. Execute por ABRIR.bat."""
import importlib.util
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3,11):
        raise RuntimeError('Instale Python 3.11 ou superior, 64 bits. Este aplicativo usa o mesmo tipo de ambiente do banco principal.')
    if platform.architecture()[0] != '64bit':
        raise RuntimeError('Use uma instalação de Python de 64 bits.')
    print('Banco de Questoes Local — preparando abertura',flush=True)
    print('Python selecionado:',sys.executable,flush=True)
    venv = ROOT/'.venv'
    python = venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():
        print('Criando ambiente privado nesta pasta...',flush=True)
        subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
    check = subprocess.run([str(python),'-c','import pymupdf; assert pymupdf.VersionBind == "1.26.6"'],capture_output=True)
    if check.returncode:
        print('Instalando leitor de PDF...',flush=True)
        wheels = ROOT/'dependencias'
        args=[str(python),'-m','pip','install','--disable-pip-version-check']
        if os.name=='nt' and any(wheels.glob('*win_amd64.whl')):
            subprocess.run(args+['--no-index','--find-links',str(wheels),'PyMuPDF==1.26.6'],check=True)
        else:
            print('Esta plataforma precisa de internet apenas para instalar a dependencia.',flush=True)
            subprocess.run(args+['PyMuPDF==1.26.6'],check=True)
    subprocess.run([str(python),str(ROOT/'servidor.py')],cwd=ROOT,check=True)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Exception as e:
        log=ROOT/'erro_abertura.txt'
        log.write_text(traceback.format_exc(),encoding='utf-8')
        print('\nNao foi possivel abrir: '+str(e)+'\nDetalhes em erro_abertura.txt',flush=True)
        sys.exit(1)
