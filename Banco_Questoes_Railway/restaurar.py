"""Restauração offline com validação e salvaguarda do banco atual."""
import argparse
import json
import os
import re
import shutil
import socket
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def validar_backup(arquivo,destino):
    with zipfile.ZipFile(arquivo) as z:
        infos=z.infolist()
        names=[i.filename for i in infos]
        if len(names)!=len(set(names)):raise ValueError('Backup contém nomes duplicados.')
        if sum(i.file_size for i in infos)>20*1024**3:raise ValueError('Backup excede o limite de 20 GB.')
        manifest=json.loads(z.read('manifesto.json'))
        if manifest.get('aplicativo')!='banco_questoes_local' or manifest.get('schema')!=1:
            raise ValueError('Este ZIP não é um backup compatível do Banco Local.')
        for info in infos:
            name=info.filename
            if name=='manifesto.json':continue
            if name!='dados/banco.sqlite' and not re.fullmatch(r'dados/fontes/[a-f0-9]{64}\.pdf',name):
                raise ValueError('Arquivo inesperado no backup: '+name)
            relative=Path(name).relative_to('dados')
            target=Path(destino)/relative;target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst)
    db=Path(destino)/'banco.sqlite'
    if not db.is_file():raise ValueError('Banco ausente no backup.')
    c=sqlite3.connect(db)
    try:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco danificado.')
        if c.execute("SELECT valor FROM meta WHERE chave='schema'").fetchone()[0]!='1':raise ValueError('Versão incompatível.')
        expected={'provas','questoes','assuntos','tentativas','cadernos','caderno_questoes','sessoes','importacoes','meta'}
        actual={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not expected.issubset(actual):raise ValueError('Estrutura incompleta no backup.')
        if c.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Relações inválidas no backup.')
        from banco import identidade_pdf
        for sha, in c.execute('SELECT id FROM provas'):
            p=Path(destino)/'fontes'/(sha+'.pdf')
            if not p.is_file() or identidade_pdf(p)!=sha:raise ValueError('PDF ausente ou divergente: '+sha)
    finally:c.close()
    return manifest


def restaurar(arquivo,pasta):
    pasta=Path(pasta).resolve();parent=pasta.parent
    lock=pasta/'servidor.json'
    if lock.exists():
        cfg=json.loads(lock.read_text(encoding='utf-8'))
        with socket.socket() as s:
            s.settimeout(1)
            if s.connect_ex(('127.0.0.1',int(cfg['porta'])))==0:
                raise ValueError('Feche o terminal do aplicativo antes de restaurar.')
    parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='validar_backup_',dir=parent) as tmp:
        validar_backup(arquivo,tmp)
        anterior=parent/('dados_antes_restauracao_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        if pasta.exists():os.replace(pasta,anterior)
        try:os.replace(tmp,pasta)
        except Exception:
            if anterior.exists():os.replace(anterior,pasta)
            raise
    return anterior if anterior.exists() else None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('arquivo',nargs='?');parser.add_argument('--dados',default=str(ROOT/'dados'));parser.add_argument('--confirmar',action='store_true')
    args=parser.parse_args();arquivo=args.arquivo
    if not arquivo:
        try:
            import tkinter as tk
            from tkinter.filedialog import askopenfilename
            root=tk.Tk();root.withdraw();arquivo=askopenfilename(title='Escolha o backup do Banco Local',filetypes=[('Backup ZIP','*.zip')]);root.destroy()
        except Exception:arquivo=input('Caminho completo do ZIP de backup: ').strip().strip('"')
    if not arquivo:return
    print('Restaurar:',arquivo)
    print('Os dados atuais serão preservados em uma pasta de segurança.')
    if not args.confirmar and input('Digite RESTAURAR para confirmar: ').strip()!='RESTAURAR':
        print('Cancelado.');return
    anterior=restaurar(arquivo,args.dados)
    print('Backup restaurado. Abra ABRIR.bat.')
    if anterior:print('Dados anteriores:',anterior)


if __name__=='__main__':
    try:main()
    except Exception as e:print('Não foi possível restaurar: '+str(e));raise SystemExit(1)
