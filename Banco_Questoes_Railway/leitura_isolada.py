"""Executa uma extração em processo separado: falha nativa não encerra o servidor."""
import json,os,subprocess,sys,tempfile
from pathlib import Path

def executar(path,destino,timeout=180):
    destino=Path(destino).resolve();destino.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bq_leitura_') as td:
        request=Path(td)/'pedido.json';result=Path(td)/'resultado.json'
        request.write_text(json.dumps({'pdf':str(Path(path).resolve()),'destino':str(destino),'resultado':str(result)}),encoding='utf-8')
        env=os.environ.copy();env.pop('PYTHONFAULTHANDLER',None)
        try:
            p=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(request)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout,env=env)
        except subprocess.TimeoutExpired:
            raise ValueError(f'Leitura excedeu {timeout} segundos; processo encerrado. PDF: {Path(path).name}') from None
        if p.returncode:
            raise ValueError(f'Leitor de PDF encerrou inesperadamente (código {p.returncode}). Arquivo: {Path(path).name}. O aplicativo foi preservado.')
        if not result.exists():raise ValueError('Leitor terminou sem resultado: '+Path(path).name)
        data=json.loads(result.read_text(encoding='utf-8'))
        if 'erro' in data:raise ValueError(data['erro'])
        return data['prova'],data['questoes']

if __name__=='__main__':
    import faulthandler
    faulthandler.disable()  # evita repetição ilimitada do relatório fatal do Windows
    req=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    try:
        from importador import extrair
        prova,questoes=extrair(Path(req['pdf']),Path(req['destino']))
        data={'prova':prova,'questoes':questoes}
    except Exception as e:data={'erro':type(e).__name__+': '+str(e)}
    Path(req['resultado']).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
