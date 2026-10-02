"""Servidor em loopback, com classificação remota opcional configurada pelo usuário."""
import argparse
import base64
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import threading
import traceback
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from banco import Banco, agora, identidade_pdf

ROOT = Path(__file__).resolve().parent
VERSAO = '1.3.1'


class Aplicacao:
    def __init__(self, pasta):
        self.pasta = Path(pasta).resolve()
        self.banco = Banco(self.pasta)
        self.fontes = self.pasta/'fontes'; self.fontes.mkdir(exist_ok=True)
        self.entrada = self.pasta/'entrada';self.entrada.mkdir(exist_ok=True)
        self.cache = self.pasta/'cache';self.cache.mkdir(exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.job_lock = threading.Lock()
        self.job = {'ativo':False,'total':0,'feitos':0,'novas':0,'atual':'','resultados':[],'parar':False}
        from ia_servico import ServicoIA
        self.ia=ServicoIA(self)

    def pdf(self, id):
        if not re.fullmatch('[a-f0-9]{64}',id or ''):
            raise ValueError('Identificação de PDF inválida.')
        path = self.fontes/(id+'.pdf')
        if not path.is_file(): raise ValueError('PDF original ausente. Importe a prova original para restaurar a cópia.')
        from fontes_pdf import verificar
        problema = verificar(path,id)
        if problema: raise ValueError(problema)
        return path

    def importar(self, nomes=None):
        with self.job_lock:
            if self.job['ativo']: raise ValueError('Já existe uma importação em andamento.')
            if self.ia.job['ativo']:raise ValueError('Pause a classificação antes de importar novas provas.')
            if nomes is None:
                files = sorted((ROOT/'provas_entrada').rglob('*.pdf'))+sorted(self.entrada.glob('*.pdf'))
            else:
                files = []
                for nome in nomes:
                    if Path(nome).name != nome or not nome.lower().endswith('.pdf'):
                        raise ValueError('Nome de arquivo inválido.')
                    p = self.entrada/nome
                    if not p.is_file(): raise ValueError('Arquivo enviado não encontrado.')
                    files.append(p)
            files = list(dict.fromkeys(files))
            if not files: raise ValueError('Escolha PDFs ou coloque-os na pasta provas_entrada.')
            self.job = {'ativo':True,'total':len(files),'feitos':0,'novas':0,'atual':'','resultados':[],'parar':False}
        def trabalhar():
            for path in files:
                if self.job['parar']: break
                self.job['atual'] = path.name
                novas,erro = 0,''
                try:
                    from leitura_isolada import executar
                    sha = identidade_pdf(path)
                    dest = self.fontes/(sha+'.pdf')
                    if not dest.exists() or identidade_pdf(dest)!=sha:
                        temp = dest.with_suffix('.tmp');shutil.copyfile(path,temp);os.replace(temp,dest)
                    try:
                        existing = self.banco.prova(sha)
                    except ValueError:
                        existing = None
                    if existing and not existing['erro']:
                        self.job['resultados'].append({'arquivo':path.name,'novas':0,'erro':'','nota':'Prova já importada; edições e histórico preservados.'})
                        self.job['feitos'] += 1
                        continue
                    try:
                        prova,questoes = executar(path,self.pasta,timeout=180)
                        novas = self.banco.registrar_prova(prova,questoes)
                    except Exception as exc:
                        erro = str(exc)
                        # O PDF permanece acessível mesmo sem perfil de extração.
                        prova = {'id':sha,'arquivo':path.name,'banca':'','paginas':0}
                        novas = self.banco.registrar_prova(prova,[],erro)
                except Exception as exc:
                    erro = str(exc)
                self.job['novas'] += novas
                self.job['feitos'] += 1
                self.job['resultados'].append({'arquivo':path.name,'novas':novas,'erro':erro})
            self.job['atual'] = '';self.job['ativo'] = False
        threading.Thread(target=trabalhar,daemon=True).start()
        return self.job

    def imagem(self, id, tipo, indice, sessao=None):
        from recorte_isolado import renderizar
        if sessao:
            q = next((q for q in self.banco.sessao(sessao)['questoes'] if q['id']==id),None)
            if not q: raise ValueError('Questão não encontrada no simulado.')
        else:
            q = self.banco.questao(id)
        pdf = self.pdf(q['prova_id'])
        segs = q.get('segmentos_contexto' if tipo=='contexto' else 'segmentos',[])
        if indice < 0 or indice >= len(segs): raise ValueError('Recorte não encontrado.')
        seg = segs[indice]
        st = pdf.stat()
        key = hashlib.sha256((str(pdf)+str(st.st_mtime_ns)+json.dumps(seg,sort_keys=True)).encode()).hexdigest()
        dest = self.cache/(key+'.png')
        if not dest.exists():
            data = renderizar(pdf,seg)
            dest.write_bytes(data)
        return dest

    def backup(self):
        if self.job['ativo']: raise ValueError('Aguarde a importação terminar antes de fazer backup.')
        out = self.pasta/'backups';out.mkdir(exist_ok=True)
        dest = out/('Banco_Local_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip')
        with self.banco.lock, tempfile.TemporaryDirectory() as td:
            db = Path(td)/'banco.sqlite';self.banco.backup_sqlite(db)
            with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifesto.json',json.dumps({'aplicativo':'banco_questoes_local','schema':1,'versao':VERSAO,'criado':agora()}))
                z.write(db,'dados/banco.sqlite')
                for p in sorted(self.fontes.glob('*.pdf')):
                    self.pdf(p.stem)
                    z.write(p,'dados/fontes/'+p.name)
        return dest


def handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'BancoLocal/1'

        def log_message(self,fmt,*args):
            if args and str(args[0]).startswith(('POST','GET /api')):
                print(fmt%args,flush=True)

        def _validar_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

        def _enviar(self,data,status=200,mime='application/json; charset=utf-8',nome=None):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Frame-Options','SAMEORIGIN')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            if nome:self.send_header('Content-Disposition','attachment; filename="'+nome+'"')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._validar_host():return self._enviar({'erro':'Host inválido.'},403)
            p = urlparse(self.path); qs = {k:v[-1] for k,v in parse_qs(p.query).items()}
            try:
                if p.path == '/api/inicio':
                    self._enviar({'token':app.token,'versao':VERSAO,'catalogo':app.banco.catalogo(),'provas':app.banco.provas(),'cadernos':app.banco.cadernos()})
                elif p.path == '/api/painel':self._enviar(app.banco.painel())
                elif p.path == '/api/questoes':
                    f = json.loads(qs.get('filtro','{}'));self._enviar(app.banco.listar(f))
                elif p.path == '/api/questao':
                    editar = qs.get('editar')=='1'
                    if editar and self.headers.get('X-Local-Token') != app.token:raise ValueError('Reabra o aplicativo.')
                    self._enviar(app.banco.publicar(app.banco.questao(qs['id']),revelar=editar))
                elif p.path == '/api/historico':self._enviar(app.banco.historico(qs.get('id')))
                elif p.path == '/api/cadernos':self._enviar(app.banco.cadernos())
                elif p.path == '/api/provas':self._enviar(app.banco.provas())
                elif p.path == '/api/importacao':self._enviar(app.job)
                elif p.path == '/api/ia':self._enviar(app.ia.estado())
                elif p.path == '/api/ia/relatorio':
                    rows=app.banco.relatorio_ia(qs.get('prova_id',''))
                    campos=['id','prova','numero','disciplina','classificacao','revisao','estado_analise','metodo','versao_motor','assuntos_sugeridos','motivo','alertas_conteudo']
                    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=campos,delimiter=';');writer.writeheader()
                    # CSV aberto em planilhas: texto do PDF não vira fórmula.
                    for row in rows:
                        writer.writerow({k:("'"+str(row[k]) if str(row[k]).lstrip().startswith(('=','+','-','@')) else row[k]) for k in campos})
                    self._enviar(out.getvalue().encode('utf-8-sig'),mime='text/csv; charset=utf-8',nome='diagnostico_classificacao.csv')
                elif p.path == '/api/sessoes':self._enviar(app.banco.sessoes())
                elif p.path == '/api/sessao':self._enviar(app.banco.sessao(qs['id']))
                elif p.path == '/api/imagem':
                    file = app.imagem(qs['id'],qs.get('tipo','questao'),int(qs.get('indice',0)),qs.get('sessao'))
                    self._enviar(file.read_bytes(),mime='image/png')
                elif p.path.startswith('/pdf/'):
                    id = p.path.removeprefix('/pdf/').removesuffix('.pdf')
                    self._enviar(app.pdf(id).read_bytes(),mime='application/pdf')
                elif p.path == '/api/baixar-backup':
                    name = qs.get('nome','')
                    if not re.fullmatch(r'Banco_Local_[0-9_]+\.zip',name):raise ValueError('Backup inválido.')
                    self._enviar((app.pasta/'backups'/name).read_bytes(),mime='application/zip',nome=name)
                elif p.path == '/api/exportar':
                    f = json.loads(qs.get('filtro','{}'))
                    items = [app.banco.publicar(app.banco.questao(id),revelar=True) for id in app.banco.listar(f,ids=True)]
                    data = {'versao':VERSAO,'criado':agora(),'nota':'Exportação de estudo; não substitui o backup com PDFs e histórico. Gabaritos preservam a origem declarada.','questoes':items}
                    self._enviar(json.dumps(data,ensure_ascii=False,indent=2).encode(),nome='questoes_exportadas.json')
                else:
                    name = 'index.html' if p.path=='/' else p.path.lstrip('/')
                    if name not in ('index.html','app.js','style.css'):return self._enviar({'erro':'Não encontrado.'},404)
                    mime = {'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]
                    self._enviar((ROOT/'web'/name).read_bytes(),mime=mime)
            except (ValueError,KeyError,FileNotFoundError,json.JSONDecodeError) as e:self._enviar({'erro':str(e)},400)
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception:
                traceback.print_exc();self._enviar({'erro':'Falha interna. Confira o terminal; seus dados permanecem salvos.'},500)

        def do_POST(self):
            if not self._validar_host() or self.headers.get('X-Local-Token')!=app.token:
                return self._enviar({'erro':'Solicitação inválida. Reabra a página do aplicativo.'},403)
            p = urlparse(self.path)
            try:
                size = int(self.headers.get('Content-Length',0))
                if p.path == '/api/enviar-pdf':
                    if not 5 <= size <= 100*1024*1024:raise ValueError('O PDF deve ter no máximo 100 MB.')
                    qs = parse_qs(p.query);nome = qs.get('nome',['prova.pdf'])[-1]
                    nome = re.sub(r'[^\w.() -]','_',Path(nome.replace('\\','/')).name,flags=re.UNICODE)[:160]
                    if not nome.lower().endswith('.pdf'):raise ValueError('Escolha um arquivo PDF.')
                    data = self.rfile.read(size)
                    if not data.startswith(b'%PDF-'):raise ValueError('O arquivo enviado não é um PDF reconhecido.')
                    # Nome original é mantido para seleção do perfil e metadados.
                    dest = app.entrada/nome
                    if dest.exists() and dest.read_bytes()!=data:
                        nome = Path(nome).stem+'-'+hashlib.sha256(data).hexdigest()[:8]+'.pdf';dest=app.entrada/nome
                    tmp=dest.with_suffix('.upload');tmp.write_bytes(data);os.replace(tmp,dest)
                    return self._enviar({'nome':nome})
                if size > 8*1024*1024:raise ValueError('Requisição muito grande.')
                b = json.loads(self.rfile.read(size) or b'{}')
                if p.path == '/api/questao':result=app.banco.salvar_questao(b)
                elif p.path == '/api/lote':result=app.banco.lote(b)
                elif p.path == '/api/pessoal':result=app.banco.pessoal(b)
                elif p.path == '/api/responder':result=app.banco.responder(b)
                elif p.path == '/api/caderno':result=app.banco.caderno(b)
                elif p.path == '/api/prova':result=app.banco.salvar_prova(b)
                elif p.path == '/api/importar':result=app.importar(b.get('nomes'))
                elif p.path == '/api/parar-importacao':app.job['parar']=True;result={'ok':True}
                elif p.path == '/api/ia/iniciar':result=app.ia.iniciar(b)
                elif p.path == '/api/ia/pausar':result=app.ia.pausar()
                elif p.path == '/api/ia/configurar-api':result=app.ia.configurar_api(b)
                elif p.path == '/api/ia/testar-api':result=app.ia.testar_api()
                elif p.path == '/api/gabarito-previa':result=app.banco.gabarito_prever(b)
                elif p.path == '/api/gabarito-salvar':result=app.banco.gabarito_salvar(b)
                elif p.path == '/api/sessao':result=app.banco.criar_sessao(b)
                elif p.path == '/api/responder-sessao':result=app.banco.responder_sessao(b)
                elif p.path == '/api/finalizar-sessao':result=app.banco.finalizar(b['id'])
                elif p.path == '/api/configurar':result=app.banco.configurar(b)
                elif p.path == '/api/backup':result={'nome':app.backup().name}
                else:return self._enviar({'erro':'Rota não encontrada.'},404)
                self._enviar(result if result is not None else {'ok':True})
            except (ValueError,KeyError,sqlite3.IntegrityError) as e:self._enviar({'erro':str(e)},400)
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception:
                traceback.print_exc();self._enviar({'erro':'Falha interna. Confira o terminal; seus dados permanecem salvos.'},500)
    return Handler


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dados',default=str(ROOT/'dados'))
    parser.add_argument('--porta',type=int,default=8767)
    parser.add_argument('--sem-navegador',action='store_true')
    args=parser.parse_args()
    app=Aplicacao(args.dados)
    try:server=ThreadingHTTPServer(('127.0.0.1',args.porta),handler(app))
    except OSError:
        raise SystemExit('A porta '+str(args.porta)+' já está em uso. Feche a outra janela do Banco Local ou escolha --porta 8768.')
    server.daemon_threads=True
    lockfile=app.pasta/'servidor.json';lockfile.write_text(json.dumps({'pid':os.getpid(),'porta':args.porta}),encoding='utf-8')
    url=f'http://127.0.0.1:{args.porta}'
    print('\nBanco de Questões Local '+VERSAO+'\n'+url+'\nMantenha esta janela aberta. Ctrl+C encerra.\n',flush=True)
    if not args.sem_navegador:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:print('\nEncerrando. Dados salvos.',flush=True)
    finally:
        app.ia.encerrar()
        server.server_close()
        lockfile.unlink(missing_ok=True)


if __name__=='__main__':main()
