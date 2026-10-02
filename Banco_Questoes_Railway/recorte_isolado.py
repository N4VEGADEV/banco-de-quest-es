"""Renderiza recorte em subprocesso com limite de tempo."""
import json,os,subprocess,sys,tempfile
from pathlib import Path

def renderizar(pdf,segmento,timeout=30):
    with tempfile.TemporaryDirectory(prefix='bq_recorte_') as td:
        root=Path(td);req=root/'pedido.json';out=root/'recorte.png';err=root/'erro.json'
        req.write_text(json.dumps({'pdf':str(Path(pdf).resolve()),'segmento':segmento,'out':str(out),'erro':str(err)}),encoding='utf-8')
        env=os.environ.copy();env.pop('PYTHONFAULTHANDLER',None)
        try:
            p=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(req)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout,env=env)
        except subprocess.TimeoutExpired:raise ValueError('Tempo limite ao gerar o recorte. Confira o PDF original.') from None
        if p.returncode:raise ValueError('Leitor encerrou ao gerar recorte (código '+str(p.returncode)+'). Confira o PDF original.')
        if err.exists():raise ValueError(json.loads(err.read_text(encoding='utf-8'))['erro'])
        if not out.exists():raise ValueError('Leitor não produziu o recorte')
        return out.read_bytes()

if __name__=='__main__':
    import faulthandler
    faulthandler.disable()
    req=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        import fitz
        seg=req['segmento']
        with fitz.open(req['pdf']) as doc:
            page=doc[int(seg['pagina'])-1];rect=fitz.Rect(seg['bbox']) & page.rect
            if rect.is_empty or rect.is_infinite:raise ValueError('Coordenadas inválidas para o recorte')
            page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),clip=rect).save(req['out'])
    except Exception as e:
        Path(req['erro']).write_text(json.dumps({'erro':'Não foi possível gerar o recorte: '+type(e).__name__+'. Verifique a integridade do PDF original.'}),encoding='utf-8')
