"""Instala o classificador opcional no ambiente privado, uma única vez."""
import hashlib
import os
import platform
import subprocess
import sys
import traceback
import urllib.request
from pathlib import Path
from ia_comum import RAIZ, MODELO_DIR, MODELO_REPO, MODELO_COMMIT, ARQUIVOS_MODELO, verificar_modelo


def hash_arquivo(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def baixar_modelo(pasta=MODELO_DIR):
    pasta=Path(pasta);pasta.mkdir(parents=True,exist_ok=True)
    for nome,(origem,tamanho,sha) in ARQUIVOS_MODELO.items():
        destino=pasta/nome
        if destino.is_file() and destino.stat().st_size==tamanho and hash_arquivo(destino)==sha:
            print(nome+': ja instalado e verificado.',flush=True);continue
        url=f'https://huggingface.co/{MODELO_REPO}/resolve/{MODELO_COMMIT}/{origem}?download=true'
        print(f'Baixando {nome} ({tamanho/1000000:.1f} MB)...',flush=True)
        tmp=destino.with_suffix('.download');feito=0;proximo=10
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'BancoQuestoesLocal/1.2'})
            with urllib.request.urlopen(req,timeout=90) as r,tmp.open('wb') as f:
                while bloco:=r.read(1024*1024):
                    feito+=len(bloco)
                    if feito>tamanho:raise ValueError('O download tem tamanho inesperado.')
                    f.write(bloco)
                    percent=int(feito/tamanho*100)
                    if percent>=proximo:print(f'  {percent}%',flush=True);proximo=percent+10
            if feito!=tamanho or hash_arquivo(tmp)!=sha:
                raise ValueError('Falha na verificacao do download. Execute novamente com uma conexao estavel.')
            os.replace(tmp,destino)
        finally:tmp.unlink(missing_ok=True)
    verificar_modelo(pasta)


def main():
    if sys.version_info<(3,11) or sys.version_info>=(3,14) or platform.architecture()[0]!='64bit':
        raise RuntimeError('Para esta versao da IA, use Python 3.11, 3.12 ou 3.13, 64 bits. Execute, por exemplo: py -3.12 instalar_ia.py')
    print('Classificador local - instalacao opcional em CPU',flush=True)
    print('Internet apenas nesta instalacao. Modelo: cerca de 136 MB, mais dependencias.',flush=True)
    print('Reserve 1 GB livre em disco. Nenhuma prova sera enviada.',flush=True)
    pasta=RAIZ/'.venv';python=pasta/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():subprocess.run([sys.executable,'-m','venv',str(pasta)],check=True)
    check=subprocess.run([str(python),'-c','import sys; assert (3,11)<=sys.version_info<(3,14)'],capture_output=True)
    if check.returncode:
        raise RuntimeError('O ambiente .venv usa Python incompativel com a IA. Feche o banco, renomeie somente .venv para .venv_antigo e execute este instalador com Python 3.11, 3.12 ou 3.13. Preserve a pasta dados.')
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(RAIZ/'requirements-ia.txt')],check=True)
    baixar_modelo()
    codigo='from classificador import Classificador; Classificador().carregar(); print("Modelo carregado em CPU com sucesso.")'
    subprocess.run([str(python),'-c',codigo],cwd=RAIZ,check=True)
    print('\nPronto. Abra ABRIR.bat e escolha Classificacao local.',flush=True)


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:
        print('\nInstalacao interrompida. Os arquivos concluidos ficam salvos.');sys.exit(1)
    except Exception as e:
        (RAIZ/'erro_instalacao_ia.txt').write_text(traceback.format_exc(),encoding='utf-8')
        print('\nNao foi possivel instalar: '+str(e)+'\nConsulte erro_instalacao_ia.txt.',flush=True);sys.exit(1)
