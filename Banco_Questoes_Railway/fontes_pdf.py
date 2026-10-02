"""Confere a cópia pelo SHA-256 registrado; não altera questões ou histórico."""
import hashlib,os,tempfile,shutil,uuid
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1024)
def _hash(path,size,mtime,ctime):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def verificar(path,sha):
    path=Path(path)
    try:
        st=path.stat()
        if not path.is_file():return 'PDF original ausente'
        if _hash(str(path.resolve()),st.st_size,st.st_mtime_ns,st.st_ctime_ns)!=sha:
            return 'Cópia do PDF divergente do original: restaure pela importação'
    except FileNotFoundError:return 'PDF original ausente'
    except OSError as e:return 'Não foi possível ler o PDF: '+str(e)
    return None

def restaurar(origem,destino,sha):
    origem=Path(origem);destino=Path(destino)
    if verificar(destino,sha) is None:return False
    destino.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='restaurando_',suffix='.pdf',dir=destino.parent);os.close(fd);tmp=Path(tmp)
    try:
        shutil.copyfile(origem,tmp)
        if verificar(tmp,sha):raise ValueError('A cópia não corresponde ao PDF registrado; verifique o arquivo de origem e o armazenamento')
        if destino.exists():
            backup=destino.parent/'copias_divergentes';backup.mkdir(exist_ok=True)
            shutil.copyfile(destino,backup/(destino.stem+'-'+uuid.uuid4().hex+'.pdf'))
        os.replace(tmp,destino)
        return True
    finally:
        if tmp.exists():tmp.unlink()
