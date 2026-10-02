"""Lotes de classificação em processo separado, com pausa e retomada."""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from ia_comum import RAIZ, MODELO_DIR, pendente, situacao_modelo


class ServicoIA:
    def __init__(self,app,pasta_modelo=None):
        self.app=app;self.pasta_modelo=Path(pasta_modelo or MODELO_DIR)
        self.lock=threading.Lock();self.parar=threading.Event();self.processo=None
        self.registro=app.pasta/'classificacao_ia.json'
        from api_claude import ConfigAPI
        self.api_config=ConfigAPI(app.pasta)
        self.job={'ativo':False,'total':0,'feitos':0,'automaticas':0,'revisar':0,'incompletas':0,
                  'fora_catalogo':0,'regras':0,'semanticas':0,'falhas':0,
                  'preservadas':0,'atual':'','erro':'','pausada':False,'segundos':0,'resultados':[]}
        try:
            antigo=json.loads(self.registro.read_text(encoding='utf-8'))
            if antigo.get('ativo'):antigo.update(ativo=False,pausada=True,atual='Lote interrompido. Inicie novamente para continuar pelas questões restantes.')
            self.job.update(antigo)
        except (OSError,ValueError):pass

    def salvar_estado(self):
        p=self.registro.with_suffix('.tmp')
        p.write_text(json.dumps(self.job,ensure_ascii=False),encoding='utf-8');os.replace(p,self.registro)

    def estado(self):
        return {'instalacao':situacao_modelo(self.pasta_modelo),'api':self.api_config.publico(),
                'job':dict(self.job),'acervo':self.app.banco.resumo_ia()}

    def configurar_api(self,b):
        with self.lock:
            if self.job['ativo']:raise ValueError('Pause e aguarde o lote terminar antes de alterar a API.')
            return self.api_config.salvar(b)

    def testar_api(self):
        return self.api_config.cliente().modelos()

    def iniciar(self,b):
        with self.lock:
            if self.job['ativo']:raise ValueError('Já existe uma classificação em andamento.')
            if self.app.job['ativo']:raise ValueError('Aguarde a importação terminar antes de classificar.')
            modo=b.get('modo','hibrido')
            if modo not in ('hibrido','regras','api'):raise ValueError('Escolha Regras, IA local ou Claude por API.')
            if modo=='hibrido' and not situacao_modelo(self.pasta_modelo)['disponivel']:
                raise ValueError('Instale a IA uma vez pelo arquivo INSTALAR_IA.bat e reabra o aplicativo.')
            threads=int(b.get('threads',2))
            if threads not in (1,2,4,8,16):raise ValueError('Escolha 1, 2, 4, 8 ou 16 threads.')
            limite=int(b.get('limite',100))
            if limite not in (25,100,500,0):raise ValueError('Escolha um tamanho de lote válido.')
            filtro={'prova_id':b.get('prova_id','')}
            if modo=='api':
                from api_claude import ClassificadorAPI
                cliente=self.api_config.cliente()
                if not cliente.config['modelo']:raise ValueError('Informe o modelo Claude na configuração da API.')
                motor=ClassificadorAPI(cliente,self.app.banco.catalogo())
                self.parar.clear()
                self.job={'ativo':True,'total':0,'feitos':0,'automaticas':0,'revisar':0,'incompletas':0,
                          'fora_catalogo':0,'regras':0,'semanticas':0,'falhas':0,'api':0,'requisicoes':0,
                          'tokens_entrada':0,'tokens_saida':0,'tokens_cache':0,'modo':'api',
                          'preparando':True,'preservadas':0,'atual':'Preparando a fila da API…',
                          'erro':'','pausada':False,'segundos':0,'resultados':[],
                          'prova_id':filtro['prova_id'],'threads':1,'limite':limite,
                          'somente_pendentes':bool(b.get('somente_pendentes',True))}
                self.salvar_estado()
                threading.Thread(target=self._trabalhar_api,args=(motor,filtro['prova_id'],limite,
                    bool(b.get('reanalisar')),bool(b.get('somente_pendentes',True))),daemon=True).start()
                return dict(self.job)
            ids=self.app.banco.listar(filtro,ids=True)
            # Não mantém enunciados/PDFs de todo o acervo na memória.
            alvos=[]
            for id in ids:
                q=self.app.banco.questao(id)
                if q['classificacao']=='revisada' or q['revisao']=='retida':continue
                if pendente(q,modo) or (b.get('reanalisar') and q['classificacao']=='pendente'):
                    alvos.append(id)
                    if limite and len(alvos)>=limite:break
            if not alvos:raise ValueError('Nenhuma questão nova para analisar neste filtro. As análises já feitas e as classificações manuais foram preservadas.')
            self.parar.clear()
            self.job={'ativo':True,'total':len(alvos),'feitos':0,'automaticas':0,'revisar':0,'incompletas':0,
                      'fora_catalogo':0,'regras':0,'semanticas':0,'falhas':0,'modo':modo,
                      'preservadas':0,'atual':'Carregando modelo local…','erro':'','pausada':False,'segundos':0,
                      'prova_id':filtro['prova_id'],'threads':threads,'limite':limite,'resultados':[]}
            self.salvar_estado()
            threading.Thread(target=self._trabalhar,args=(alvos,threads,modo),daemon=True).start()
            return dict(self.job)

    def pausar(self):
        self.parar.set()
        return {'ok':True}

    def encerrar(self):
        self.parar.set()
        p=self.processo
        if p and p.poll() is None:
            p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill()

    def _trabalhar_api(self,motor,prova_id,limite,reanalisar,somente_pendentes):
        from api_claude import ErroAPI
        inicio=time.monotonic()
        try:
            alvos=[];apos=''
            while not self.parar.is_set():
                ids=self.app.banco.candidatas_ia(prova_id,apos,somente_pendentes)
                if not ids:break
                for id in ids:
                    if self.parar.is_set():break
                    q=self.app.banco.questao(id)
                    if motor.pendente(q,reanalisar):alvos.append(id)
                    if limite and len(alvos)>=limite:break
                if limite and len(alvos)>=limite:break
                apos=ids[-1]
            self.job.update(total=len(alvos),preparando=False)
            self.salvar_estado()
            if not alvos and not self.parar.is_set():
                self.job['atual']='Nenhuma questão nova neste filtro. As análises concluídas e revisões foram preservadas.'
            for id in alvos:
                if self.parar.is_set():break
                q=self.app.banco.questao(id)
                if q['classificacao']=='revisada' or q['revisao']=='retida' or (somente_pendentes and q['classificacao']!='pendente'):
                    self.job['preservadas']+=1;self.job['feitos']+=1;continue
                self.job['atual']=f"Claude · Q{q['numero']} · {q['prova'].get('nome','')}"
                self.salvar_estado()
                # Uma requisição por vez; nenhum retry pago automático.
                r=motor.classificar(q)
                self.job['requisicoes']=motor.requisicoes
                uso=r.get('uso_tokens') or {}
                self.job['tokens_entrada']+=uso.get('entrada',0)
                self.job['tokens_saida']+=uso.get('saida',0)
                self.job['tokens_cache']+=uso.get('cache_criado',0)+uso.get('cache_lido',0)
                status=self.app.banco.salvar_analise_ia(id,q['versao'],r)
                campo={'automatica':'automaticas','revisar':'revisar','incompleta':'incompletas',
                       'fora_catalogo':'fora_catalogo','preservada':'preservadas'}[status]
                self.job[campo]+=1;self.job['feitos']+=1
                if status=='automatica':self.job['api']+=1
                if r.get('codigo_motivo')=='api_resposta_invalida':self.job['falhas']+=1
                self.job['segundos']=round(time.monotonic()-inicio,1)
                self.job['resultados'].append({'id':id,'numero':q['numero'],'prova':q['prova']['nome'],
                    'estado':status,'disciplina':r.get('disciplina',''),'assuntos':r.get('assuntos',[]),'motivo':r.get('motivo','')})
                self.job['resultados']=self.job['resultados'][-30:]
                self.salvar_estado()
                if self.parar.wait(.2):break
        except (ErroAPI,ValueError) as exc:
            self.job['erro']=str(exc);self.job['pausada']=True
        except Exception:
            # Não registra exceptions externas que possam conter a chave.
            self.job['erro']='Falha ao processar o lote da API. Os resultados anteriores estão salvos.'
            self.job['pausada']=True
        finally:
            self.job.update(ativo=False,preparando=False,pausada=self.parar.is_set() or self.job['pausada'],
                            segundos=round(time.monotonic()-inicio,1),requisicoes=motor.requisicoes)
            self.salvar_estado()

    def _trabalhar(self,ids,threads,modo='hibrido'):
        inicio=time.monotonic();p=None;log=None
        try:
            log=(self.app.pasta/'classificacao_ia.log').open('w',encoding='utf-8')
            env=dict(os.environ,PYTHONIOENCODING='utf-8',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1')
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
            p=subprocess.Popen([sys.executable,'-u',str(RAIZ/'classificador.py')],stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',env=env,creationflags=flags)
            self.processo=p;saida=queue.Queue()
            def ler():
                try:
                    for linha in p.stdout:saida.put(linha)
                finally:saida.put(None)
            threading.Thread(target=ler,daemon=True).start()
            def enviar(obj):
                p.stdin.write(json.dumps(obj,ensure_ascii=False)+'\n');p.stdin.flush()
            def receber(timeout=120):
                try:linha=saida.get(timeout=timeout)
                except queue.Empty:raise ValueError('A IA demorou além do limite. Tente um lote menor ou 1 thread; consulte classificacao_ia.log.')
                if linha is None:raise ValueError('O processo da IA encerrou. Consulte dados/classificacao_ia.log; os resultados concluídos estão salvos.')
                r=json.loads(linha)
                return r
            enviar({'pasta':str(self.pasta_modelo),'threads':threads,'usar_modelo':modo=='hibrido'});receber()
            secoes={}
            from classificador import secoes_cesgranrio
            for id in ids:
                if self.parar.is_set():break
                q=self.app.banco.questao(id)
                if q['classificacao']=='revisada' or q['revisao']=='retida':
                    self.job['preservadas']+=1;self.job['feitos']+=1;continue
                self.job['atual']=f"Q{q['numero']} · {q['prova'].get('nome','')}"
                pid=q['prova_id']
                if pid not in secoes:
                    try:secoes[pid]=secoes_cesgranrio(self.app.pdf(pid)) if q['prova'].get('banca','').upper()=='CESGRANRIO' else {}
                    except Exception:secoes[pid]={}
                # Apenas os campos necessários; gabarito, anotações e histórico
                # nunca entram na classificação nem são enviados ao modelo.
                campos=('enunciado','alternativas','contexto','modo_visual','revisao','segmentos','segmentos_contexto')
                enviar({'questao':{k:q.get(k) for k in campos},'pista_pdf':secoes[pid].get(q['numero'])})
                r=receber()
                if r.get('erro'):
                    from ia_comum import assinatura, VERSAO_IA
                    r={'assinatura':assinatura(q),'versao_motor':VERSAO_IA,'estado':'revisar',
                       'disciplina':'','assuntos':[],'metodo':'erro','codigo_motivo':'falha_processamento',
                       'motivo':'Falha nesta questão: '+str(r['erro'])[:500]}
                    self.job['falhas']+=1
                status=self.app.banco.salvar_analise_ia(id,q['versao'],r)
                campo={'automatica':'automaticas','revisar':'revisar','incompleta':'incompletas','fora_catalogo':'fora_catalogo','preservada':'preservadas'}[status]
                self.job[campo]+=1;self.job['feitos']+=1
                if status=='automatica':self.job['semanticas' if r.get('metodo')=='modelo_local' else 'regras']+=1
                self.job['segundos']=round(time.monotonic()-inicio,1)
                self.job['resultados'].append({'id':id,'numero':q['numero'],'prova':q['prova']['nome'],
                    'estado':status,'disciplina':r.get('disciplina',''),'assuntos':r.get('assuntos',[]),'motivo':r.get('motivo','')})
                self.job['resultados']=self.job['resultados'][-30:]
                self.salvar_estado()
        except Exception as exc:
            self.job['erro']=str(exc)
        finally:
            if p:
                try:p.stdin.close()
                except (OSError,ValueError):pass
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.terminate()
                    try:p.wait(timeout=3)
                    except subprocess.TimeoutExpired:p.kill()
            if log:log.close()
            self.processo=None
            self.job.update(ativo=False,pausada=self.parar.is_set(),atual='',segundos=round(time.monotonic()-inicio,1))
            self.salvar_estado()
