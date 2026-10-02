"""Banco local independente. Classificação explícita, histórico e sessões em SQLite."""
import contextlib
import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path


def agora():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def normalizar(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(value).lower())
                            if not unicodedata.combining(c)).split())


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def identidade_pdf(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


class Banco:
    def __init__(self, pasta):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.pasta / 'banco.sqlite'
        self.lock = threading.RLock()
        with self.con() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
            INSERT OR IGNORE INTO meta VALUES ('schema','1');
            INSERT OR IGNORE INTO meta VALUES ('intervalo','7');
            CREATE TABLE IF NOT EXISTS provas (
                id TEXT PRIMARY KEY, nome TEXT NOT NULL, banca TEXT NOT NULL DEFAULT '',
                ano TEXT NOT NULL DEFAULT '', orgao TEXT NOT NULL DEFAULT '', cargo TEXT NOT NULL DEFAULT '',
                caderno TEXT NOT NULL DEFAULT '', arquivo TEXT NOT NULL DEFAULT '',
                paginas INTEGER NOT NULL DEFAULT 0, erro TEXT NOT NULL DEFAULT '', criado TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS questoes (
                id TEXT PRIMARY KEY, prova_id TEXT REFERENCES provas(id), numero INTEGER,
                disciplina TEXT NOT NULL DEFAULT '', revisao TEXT NOT NULL DEFAULT 'pendente',
                classificacao TEXT NOT NULL DEFAULT 'pendente', favorito INTEGER NOT NULL DEFAULT 0,
                anotacao TEXT NOT NULL DEFAULT '', busca TEXT NOT NULL DEFAULT '',
                versao INTEGER NOT NULL DEFAULT 1, dados TEXT NOT NULL, atualizado TEXT NOT NULL,
                UNIQUE(prova_id, numero));
            CREATE TABLE IF NOT EXISTS assuntos (
                questao_id TEXT NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
                nome TEXT NOT NULL, PRIMARY KEY(questao_id,nome));
            CREATE TABLE IF NOT EXISTS tentativas (
                id TEXT PRIMARY KEY, questao_id TEXT NOT NULL REFERENCES questoes(id),
                sessao_id TEXT, escolha TEXT NOT NULL, correta INTEGER, chute INTEGER NOT NULL,
                segundos INTEGER NOT NULL, criado TEXT NOT NULL, proxima TEXT,
                gabarito TEXT NOT NULL DEFAULT '', fonte TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS cadernos (
                id TEXT PRIMARY KEY, nome TEXT NOT NULL, criado TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS caderno_questoes (
                caderno_id TEXT REFERENCES cadernos(id) ON DELETE CASCADE,
                questao_id TEXT REFERENCES questoes(id) ON DELETE CASCADE,
                PRIMARY KEY(caderno_id,questao_id));
            CREATE TABLE IF NOT EXISTS sessoes (
                id TEXT PRIMARY KEY, nome TEXT NOT NULL, estado TEXT NOT NULL,
                criado TEXT NOT NULL, terminado TEXT, dados TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS importacoes (
                id INTEGER PRIMARY KEY, arquivo TEXT NOT NULL, novas INTEGER NOT NULL,
                erro TEXT NOT NULL, criado TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS q_class ON questoes(revisao,classificacao,disciplina);
            CREATE INDEX IF NOT EXISTS q_prova ON questoes(prova_id,numero);
            CREATE INDEX IF NOT EXISTS a_nome ON assuntos(nome,questao_id);
            CREATE INDEX IF NOT EXISTS t_questao ON tentativas(questao_id,criado DESC,id DESC);
            CREATE INDEX IF NOT EXISTS t_sessao ON tentativas(sessao_id);
            ''')
            schema = c.execute("SELECT valor FROM meta WHERE chave='schema'").fetchone()[0]
            if schema != '1':
                raise ValueError('Versão do banco incompatível com este aplicativo.')

    @contextlib.contextmanager
    def con(self):
        with self.lock:
            c = sqlite3.connect(self.arquivo, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            try:
                with c:
                    yield c
            finally:
                c.close()

    def provas(self):
        with self.con() as c:
            return [dict(r) for r in c.execute('''SELECT p.*, count(q.id) total,
                sum(CASE WHEN q.revisao='apta' AND q.classificacao IN ('revisada','automatica') THEN 1 ELSE 0 END) prontas
                FROM provas p LEFT JOIN questoes q ON q.prova_id=p.id GROUP BY p.id ORDER BY p.criado DESC''')]

    def prova(self, id):
        with self.con() as c:
            r = c.execute('SELECT * FROM provas WHERE id=?', (id,)).fetchone()
            if not r:
                raise ValueError('Prova não encontrada.')
            return dict(r)

    def registrar_prova(self, p, questoes, erro=''):
        ano = re.search(r'(?<!\d)(20\d{2})(?!\d)', p['arquivo'])
        novas = 0
        with self.con() as c:
            c.execute('''INSERT INTO provas(id,nome,banca,ano,arquivo,paginas,erro,criado)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET erro=excluded.erro,paginas=excluded.paginas''',
                (p['id'], Path(p['arquivo']).stem, p.get('banca',''), ano[1] if ano else '',
                 p['arquivo'], p.get('paginas',0), erro, agora()))
            for raw in questoes:
                id = 'PDF-' + raw['id']
                if c.execute('SELECT 1 FROM questoes WHERE prova_id=? AND numero=?', (p['id'], raw['numero'])).fetchone():
                    continue
                q = {'id': id, 'prova_id': p['id'], 'numero': raw['numero'],
                     'enunciado': raw.get('enunciado_candidato',''),
                     'alternativas': raw.get('alternativas_candidatas',{}),
                     'contexto': '\n\n'.join(x.get('texto_extraido','') for x in raw.get('contextos_candidatos',[])),
                     'segmentos': raw.get('segmentos',[]),
                     'segmentos_contexto': [s for x in raw.get('contextos_candidatos',[]) for s in x.get('segmentos',[])],
                     'alertas': raw.get('alertas',[]), 'original': raw,
                     'gabarito': '', 'status_gabarito': 'sem', 'fonte_gabarito': '',
                     'explicacao': '', 'modo_visual': bool(any('visual' in a or 'imagem' in a or 'vetorial' in a for a in raw.get('alertas',[])))}
                self._gravar(c, q, criar=True)
                novas += 1
            c.execute('INSERT INTO importacoes(arquivo,novas,erro,criado) VALUES(?,?,?,?)', (p['arquivo'],novas,erro,agora()))
        return novas

    def salvar_prova(self, p):
        with self.con() as c:
            if not c.execute('SELECT 1 FROM provas WHERE id=?',(p['id'],)).fetchone():
                raise ValueError('Prova não encontrada.')
            c.execute('UPDATE provas SET nome=?,banca=?,ano=?,orgao=?,cargo=?,caderno=? WHERE id=?',
                tuple(str(p.get(k,'')).strip()[:400] for k in ('nome','banca','ano','orgao','cargo','caderno'))+(p['id'],))

    def _questao(self, c, id):
        r = c.execute('SELECT * FROM questoes WHERE id=?', (id,)).fetchone()
        if not r:
            raise ValueError('Questão não encontrada.')
        q = json.loads(r['dados'])
        q.update({k:r[k] for k in ('id','prova_id','numero','disciplina','revisao','classificacao','favorito','anotacao','versao','atualizado')})
        q['assuntos'] = [x[0] for x in c.execute('SELECT nome FROM assuntos WHERE questao_id=? ORDER BY nome',(id,))]
        p = c.execute('SELECT * FROM provas WHERE id=?',(q['prova_id'],)).fetchone()
        q['prova'] = dict(p) if p else {}
        t = c.execute('SELECT * FROM tentativas WHERE questao_id=? ORDER BY criado DESC,rowid DESC LIMIT 1',(id,)).fetchone()
        q['ultima'] = dict(t) if t else None
        return q

    def questao(self, id):
        with self.con() as c:
            return self._questao(c, id)

    def candidatas_ia(self,prova_id='',apos='',somente_pendentes=False):
        """Fila paginada: sem juntar tentativas ou carregar o acervo inteiro."""
        cond=["classificacao!='revisada'","revisao!='retida'","id>?"];args=[apos]
        if prova_id:cond.append('prova_id=?');args.append(prova_id)
        if somente_pendentes:cond.append("classificacao='pendente'")
        with self.con() as c:
            return [r[0] for r in c.execute('SELECT id FROM questoes WHERE '+' AND '.join(cond)+' ORDER BY id LIMIT 200',args)]

    @staticmethod
    def publicar(q, revelar=False):
        q = dict(q)
        q.pop('original', None)
        if not revelar:
            for campo in ('gabarito','fonte_gabarito','explicacao'):
                q.pop(campo,None)
            if q.get('ultima'):
                q['ultima'] = {k:v for k,v in q['ultima'].items() if k not in ('gabarito','fonte','escolha')}
        return q

    def _validar(self, q):
        if q.get('revisao','pendente') not in ('pendente','apta','retida'):
            raise ValueError('Estado de conferência inválido.')
        if q.get('classificacao','pendente') not in ('pendente','revisada','automatica'):
            raise ValueError('Estado de classificação inválido.')
        alts = q.get('alternativas',{})
        if not isinstance(alts,dict) or any(k not in 'ABCDE' for k in alts):
            raise ValueError('Use alternativas com letras A a E.')
        if q.get('revisao') == 'apta':
            if len(q.get('enunciado','').strip()) < 5 or set(alts) not in (set('AB'),set('ABCD'),set('ABCDE')) or any(not str(v).strip() for v in alts.values()):
                raise ValueError('Para liberar, preencha enunciado e todas as alternativas (A/B, A–D ou A–E). Para conteúdo visual, use uma descrição e preserve o recorte.')
            if not q.get('conferida'):
                raise ValueError('Confirme a conferência do enunciado, alternativas, texto-base e recortes.')
        if q.get('classificacao') in ('revisada','automatica') and (not q.get('disciplina','').strip() or not q.get('assuntos')):
            raise ValueError('Uma classificação revisada precisa de disciplina e pelo menos um assunto.')
        status = q.get('status_gabarito','sem')
        if status not in ('sem','oficial','informado','anulada'):
            raise ValueError('Situação de gabarito inválida.')
        if status in ('oficial','informado') and q.get('gabarito') not in alts:
            raise ValueError('O gabarito precisa corresponder a uma alternativa existente.')
        if status == 'oficial' and not q.get('fonte_gabarito','').strip():
            raise ValueError('Informe a fonte do gabarito oficial e confira a prova/caderno correspondente.')
        if status in ('sem','anulada'):
            q['gabarito'] = ''
        for key in ('segmentos','segmentos_contexto'):
            for s in q.get(key,[]):
                if not isinstance(s.get('pagina'),int) or s['pagina'] < 1 or not isinstance(s.get('bbox'),list) or len(s['bbox']) != 4:
                    raise ValueError('Recorte inválido. Informe página e quatro coordenadas.')
                x0,y0,x1,y1 = [float(x) for x in s['bbox']]
                if min(x0,y0) < 0 or x1 <= x0 or y1 <= y0 or max(x1,y1) > 20000:
                    raise ValueError('Coordenadas de recorte inválidas.')

    def _gravar(self, c, q, criar=False):
        assuntos = list(dict.fromkeys(' / '.join(p.strip() for p in str(t).split('/') if p.strip()) for t in q.get('assuntos',[]) if str(t).strip()))
        q['assuntos'] = assuntos
        busca = normalizar(q.get('enunciado','')+' '+q.get('contexto','')+' '+' '.join(map(str,q.get('alternativas',{}).values())))
        dados = {k:v for k,v in q.items() if k not in ('prova','ultima','busca')}
        if criar:
            c.execute('''INSERT INTO questoes(id,prova_id,numero,disciplina,revisao,classificacao,busca,dados,atualizado)
                VALUES(?,?,?,?,?,?,?,?,?)''', (q['id'],q.get('prova_id'),q.get('numero'),q.get('disciplina',''),q.get('revisao','pendente'),q.get('classificacao','pendente'),busca,dumps(dados),agora()))
        else:
            c.execute('''UPDATE questoes SET disciplina=?,revisao=?,classificacao=?,busca=?,dados=?,versao=versao+1,atualizado=? WHERE id=?''',
                (q.get('disciplina',''),q.get('revisao','pendente'),q.get('classificacao','pendente'),busca,dumps(dados),agora(),q['id']))
        c.execute('DELETE FROM assuntos WHERE questao_id=?',(q['id'],))
        c.executemany('INSERT INTO assuntos VALUES(?,?)',[(q['id'],a) for a in assuntos])

    def salvar_questao(self, b):
        with self.con() as c:
            novo = not b.get('id')
            if novo:
                q = {'id':'MAN-'+uuid.uuid4().hex, 'prova_id':b.get('prova_id'), 'numero':int(b.get('numero') or 0),
                     'original':{}, 'alertas':[], 'segmentos':[], 'segmentos_contexto':[], 'revisao':'pendente','classificacao':'pendente'}
                if not q['prova_id'] or q['numero'] < 1 or not c.execute('SELECT 1 FROM provas WHERE id=?',(q['prova_id'],)).fetchone():
                    raise ValueError('Escolha a prova importada e o número da questão.')
            else:
                q = self._questao(c,b['id'])
                if b.get('versao') != q['versao']:
                    raise ValueError('A questão mudou em outra tela. Reabra o editor antes de salvar.')
            from ia_comum import assinatura
            hash_antes = assinatura(q,somente_conteudo=True)
            classificacao_antes = q.get('classificacao')
            metadados_antes = (q.get('disciplina',''),set(q.get('assuntos',[])))
            for key in ('enunciado','alternativas','contexto','disciplina','assuntos','revisao','classificacao','conferida','gabarito','status_gabarito','fonte_gabarito','explicacao','modo_visual','segmentos','segmentos_contexto'):
                if key in b:
                    q[key] = b[key]
            if classificacao_antes=='automatica' and q.get('classificacao')=='automatica' and metadados_antes!=(q.get('disciplina',''),set(q.get('assuntos',[]))):
                # Alterar os assuntos no editor é uma decisão humana.
                q['classificacao']='revisada' if q.get('disciplina') and q.get('assuntos') else 'pendente'
            if not novo and assinatura(q,somente_conteudo=True) != hash_antes:
                q.pop('analise_ia',None)
                if classificacao_antes == 'automatica' and q.get('classificacao') == 'automatica':
                    q['classificacao']='pendente';q['disciplina']='';q['assuntos']=[]
            self._validar(q)
            try:
                self._gravar(c,q,criar=novo)
            except sqlite3.IntegrityError:
                raise ValueError('Já existe uma questão com esse número nesta prova.') from None
            return self._questao(c,q['id'])

    def _where(self, f):
        cond, args = ['1=1'], []
        for key, col in [('banca','p.banca'),('ano','p.ano'),('prova_id','q.prova_id'),('disciplina','q.disciplina'),('revisao','q.revisao'),('classificacao','q.classificacao')]:
            if f.get(key):
                cond.append(col+'=?'); args.append(f[key])
        if f.get('prontas'):
            cond += ["q.revisao='apta'", "q.classificacao IN ('revisada','automatica')"]
        if f.get('ia') in ('revisar','incompleta','fora_catalogo'):
            cond.append("q.classificacao='pendente' AND json_extract(q.dados,'$.analise_ia.estado')=?");args.append(f['ia'])
        elif f.get('ia') == 'sem':
            cond.append("q.classificacao='pendente' AND json_extract(q.dados,'$.analise_ia') IS NULL")
        elif f.get('ia') == 'alertas_conteudo':
            cond.append("q.revisao='pendente' AND coalesce(json_array_length(json_extract(q.dados,'$.analise_ia.alertas_conteudo')),0)>0")
        if f.get('favoritos'):
            cond.append('q.favorito=1')
        if f.get('texto'):
            cond.append('instr(q.busca,?)>0');args.append(normalizar(f['texto']))
        if f.get('assunto'):
            t = f['assunto']
            cond.append("EXISTS(SELECT 1 FROM assuntos a WHERE a.questao_id=q.id AND (a.nome=? OR substr(a.nome,1,?)=?))")
            args += [t,len(t+' / '),t+' / ']
        if f.get('caderno_id'):
            cond.append('EXISTS(SELECT 1 FROM caderno_questoes cq WHERE cq.questao_id=q.id AND cq.caderno_id=?)');args.append(f['caderno_id'])
        estado = f.get('situacao','')
        if estado == 'nao': cond.append('t.id IS NULL')
        elif estado == 'respondidas': cond.append('t.id IS NOT NULL')
        elif estado == 'certas': cond.append('t.correta=1')
        elif estado == 'erradas': cond.append('t.correta=0')
        elif estado == 'chutes': cond.append('t.chute=1')
        elif estado == 'pendentes': cond.append('t.id IS NOT NULL AND t.correta IS NULL')
        elif estado == 'revisar': cond.append('t.proxima IS NOT NULL AND t.proxima<=?');args.append(date.today().isoformat())
        if f.get('evitar_recentes'):
            cond.append('(t.proxima IS NULL OR t.proxima<=?)'); args.append(date.today().isoformat())
        if f.get('gabarito'):
            cond.append("json_extract(q.dados,'$.status_gabarito')=?");args.append(f['gabarito'])
        return ' AND '.join(cond), args

    FROM = '''FROM questoes q LEFT JOIN provas p ON p.id=q.prova_id LEFT JOIN tentativas t ON t.rowid=(
        SELECT tt.rowid FROM tentativas tt WHERE tt.questao_id=q.id ORDER BY tt.criado DESC,tt.rowid DESC LIMIT 1)'''

    def listar(self, f=None, ids=False):
        f = f or {}; where,args = self._where(f)
        with self.con() as c:
            total = c.execute('SELECT count(*) '+self.FROM+' WHERE '+where,args).fetchone()[0]
            ordem = 'q.atualizado DESC,q.id' if f.get('ordem') == 'recentes' else 'p.nome,q.numero,q.id'
            if ids:
                return [r[0] for r in c.execute('SELECT q.id '+self.FROM+' WHERE '+where+' ORDER BY '+ordem,args)]
            pagina = max(1,int(f.get('pagina',1))); limite = min(100,max(1,int(f.get('limite',20))))
            rows = c.execute('''SELECT q.id,q.numero,q.disciplina,q.revisao,q.classificacao,q.favorito,q.versao,
                json_extract(q.dados,'$.enunciado') enunciado, json_extract(q.dados,'$.status_gabarito') status_gabarito,
                p.nome prova,p.banca,p.ano,t.correta,t.chute,t.id tentativa,t.proxima '''+self.FROM+
                ' WHERE '+where+' ORDER BY '+ordem+' LIMIT ? OFFSET ?',args+[limite,(pagina-1)*limite]).fetchall()
            items = []
            for row in rows:
                q = dict(row)
                q['assuntos'] = [r[0] for r in c.execute('SELECT nome FROM assuntos WHERE questao_id=? ORDER BY nome',(q['id'],))]
                items.append(q)
            return {'total':total,'pagina':pagina,'limite':limite,'itens':items}

    def alvos(self, b):
        ids = self.listar(b['filtro'],ids=True) if 'filtro' in b else list(dict.fromkeys(b.get('ids',[])))
        if 'filtro' in b and b.get('esperado') is not None and len(ids) != int(b['esperado']):
            raise ValueError('O total do filtro mudou. Atualize a lista e selecione novamente.')
        if not ids:
            raise ValueError('Selecione pelo menos uma questão.')
        return ids

    def lote(self,b):
        ids = self.alvos(b)
        with self.con() as c:
            # A transação inteira é revertida quando uma validação falha.
            for id in ids:
                q = self._questao(c,id)
                if b.get('disciplina'): q['disciplina'] = b['disciplina'].strip()
                if b.get('assuntos'):
                    q['assuntos'] = b['assuntos'] if b.get('substituir') else list(dict.fromkeys(q['assuntos']+b['assuntos']))
                if b.get('classificacao'): q['classificacao'] = b['classificacao']
                if b.get('revisao'):
                    q['revisao'] = b['revisao'];q['conferida'] = bool(b.get('conferida'))
                self._validar(q)
                self._gravar(c,q)
        return {'alteradas':len(ids)}

    def pessoal(self,b):
        with self.con() as c:
            q = self._questao(c,b['id'])
            if 'favorito' in b:
                c.execute('UPDATE questoes SET favorito=? WHERE id=?',(bool(b['favorito']),q['id']))
            if 'anotacao' in b:
                c.execute('UPDATE questoes SET anotacao=? WHERE id=?',(str(b['anotacao'])[:30000],q['id']))

    def cadernos(self):
        with self.con() as c:
            return [dict(r) for r in c.execute('''SELECT c.*,count(cq.questao_id) total FROM cadernos c LEFT JOIN caderno_questoes cq ON cq.caderno_id=c.id GROUP BY c.id ORDER BY c.nome''')]

    def caderno(self,b):
        acao = b.get('acao','criar')
        with self.con() as c:
            if acao == 'criar':
                nome = str(b.get('nome','')).strip()[:120]
                if not nome: raise ValueError('Informe o nome do caderno.')
                id = uuid.uuid4().hex
                c.execute('INSERT INTO cadernos VALUES(?,?,?)',(id,nome,agora()))
                return {'id':id}
            if not c.execute('SELECT 1 FROM cadernos WHERE id=?',(b['id'],)).fetchone():
                raise ValueError('Caderno não encontrado.')
            if acao == 'excluir': c.execute('DELETE FROM cadernos WHERE id=?',(b['id'],))
            elif acao == 'adicionar':
                ids = self.alvos(b)
                c.executemany('INSERT OR IGNORE INTO caderno_questoes VALUES(?,?)',[(b['id'],id) for id in ids])
                return {'adicionadas':len(ids)}
            elif acao == 'remover':
                c.executemany('DELETE FROM caderno_questoes WHERE caderno_id=? AND questao_id=?',[(b['id'],id) for id in b['ids']])
            else: raise ValueError('Ação de caderno inválida.')
        return {'ok':True}

    def _responder(self,c,q,b,sessao_id=None):
        if q['revisao'] != 'apta' or q['classificacao'] not in ('revisada','automatica'):
            raise ValueError('Confira o conteúdo e a classificação antes de responder.')
        escolha = b.get('escolha','')
        if escolha not in q.get('alternativas',{}):
            raise ValueError('Escolha uma alternativa válida.')
        key = q.get('gabarito','') if q.get('status_gabarito') == 'oficial' else ''
        correta = int(escolha == key) if key else None
        chute = bool(b.get('chute')); seconds = max(0,min(86400,int(b.get('segundos',0))))
        intervalo = int(c.execute("SELECT valor FROM meta WHERE chave='intervalo'").fetchone()[0])
        dias = 1 if chute or correta == 0 else intervalo if correta == 1 else None
        proxima = (date.today()+timedelta(days=dias)).isoformat() if dias else None
        id = b.get('tentativa_id') or uuid.uuid4().hex
        existing = c.execute('SELECT * FROM tentativas WHERE id=?',(id,)).fetchone()
        if existing:
            if existing['questao_id'] != q['id'] or existing['escolha'] != escolha:
                raise ValueError('Identificador de tentativa já utilizado.')
            return dict(existing)
        c.execute('INSERT INTO tentativas VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (id,q['id'],sessao_id,escolha,correta,chute,seconds,agora(),proxima,key,q.get('fonte_gabarito','') if key else ''))
        return dict(c.execute('SELECT * FROM tentativas WHERE id=?',(id,)).fetchone())

    def responder(self,b):
        with self.con() as c:
            q = self._questao(c,b['id'])
            r = self._responder(c,q,b)
            return {'tentativa':r,'questao':self.publicar(q,revelar=True)}

    def historico(self,id=None):
        with self.con() as c:
            sql = '''SELECT t.*,q.numero,p.nome prova FROM tentativas t JOIN questoes q ON q.id=t.questao_id
                LEFT JOIN provas p ON p.id=q.prova_id'''
            if id: sql += ' WHERE t.questao_id=?'
            return [dict(r) for r in c.execute(sql+' ORDER BY t.criado DESC,t.rowid DESC LIMIT 200',(id,) if id else ())]

    def catalogo(self):
        catalog = json.loads((Path(__file__).parent/'catalogo.json').read_text(encoding='utf-8'))
        from ia_comum import catalogo_ia
        for d,assuntos in catalogo_ia()[0].items():
            catalog.setdefault(d,[]).extend(a for a in assuntos if a not in catalog.get(d,[]))
        with self.con() as c:
            for r in c.execute('SELECT DISTINCT q.disciplina,a.nome FROM questoes q JOIN assuntos a ON a.questao_id=q.id'):
                catalog.setdefault(r[0],[])
                if r[1] not in catalog[r[0]]: catalog[r[0]].append(r[1])
        for disciplina, termos in list(catalog.items()):
            todos = set(termos)
            for termo in termos:
                parts = termo.split(' / ')
                todos.update(' / '.join(parts[:i]) for i in range(1,len(parts)))
            catalog[disciplina] = sorted(todos)
        return catalog

    def painel(self):
        with self.con() as c:
            q = dict(c.execute('''SELECT count(*) total,
                coalesce(sum(revisao='apta' AND classificacao IN ('revisada','automatica')),0) prontas,
                coalesce(sum(revisao='pendente'),0) pendentes,
                coalesce(sum(classificacao='pendente'),0) sem_classificacao,
                coalesce(sum(revisao='retida'),0) retidas FROM questoes''').fetchone())
            t = dict(c.execute('''SELECT count(*) tentativas, count(correta) corrigidas,
                coalesce(sum(correta=1),0) acertos,coalesce(sum(correta=0),0) erros,
                coalesce(sum(correta IS NULL),0) sem_gabarito,coalesce(sum(chute=1),0) chutes,
                count(DISTINCT questao_id) respondidas FROM tentativas''').fetchone())
            por = [dict(r) for r in c.execute('''SELECT coalesce(nullif(q.disciplina,''),'Não classificada') disciplina,
                count(*) tentativas,count(t.correta) corrigidas,coalesce(sum(t.correta=1),0) acertos
                FROM tentativas t JOIN questoes q ON q.id=t.questao_id GROUP BY q.disciplina ORDER BY tentativas DESC''')]
            dias = [dict(r) for r in c.execute('''SELECT substr(criado,1,10) dia,count(*) total,
                coalesce(sum(correta=1),0) acertos,count(correta) corrigidas FROM tentativas GROUP BY substr(criado,1,10) ORDER BY dia DESC LIMIT 14''')]
            imports = [dict(r) for r in c.execute('SELECT * FROM importacoes ORDER BY id DESC LIMIT 12')]
            intervalo = int(c.execute("SELECT valor FROM meta WHERE chave='intervalo'").fetchone()[0])
        q['revisar'] = self.listar({'prontas':True,'situacao':'revisar'})['total']
        return {'questoes':q,'resultados':t,'disciplinas':por,'dias':dias,'importacoes':imports,'intervalo':intervalo}

    def salvar_analise_ia(self, id, versao, resultado):
        from ia_comum import assinatura
        with self.con() as c:
            q=self._questao(c,id)
            if q['versao']!=versao or assinatura(q)!=resultado.get('assinatura') or q['classificacao']=='revisada' or q['revisao']=='retida':
                return 'preservada'
            resultado=dict(resultado,analisada_em=agora())
            if resultado.get('estado') not in ('automatica','revisar','incompleta','fora_catalogo'):
                raise ValueError('Resultado de análise inválido.')
            if q['classificacao']=='automatica' and resultado.get('estado')!='automatica':
                resultado['classificacao_anterior']={'disciplina':q['disciplina'],'assuntos':q['assuntos']}
                q['disciplina']='';q['assuntos']=[];q['classificacao']='pendente'
            # Metadados manuais não revisados também são preservados.
            if resultado.get('estado')=='automatica':
                if q['classificacao']=='automatica' or (not q['disciplina'] and not q['assuntos']):
                    q['disciplina']=resultado['disciplina'];q['assuntos']=resultado['assuntos'];q['classificacao']='automatica'
                else:
                    resultado['estado']='revisar';resultado['motivo']+=' Metadados existentes preservados; confira a sugestão.'
            q['analise_ia']=resultado
            self._validar(q);self._gravar(c,q)
            return resultado['estado']

    def resumo_ia(self):
        with self.con() as c:
            r=c.execute("""SELECT count(*) total,
                coalesce(sum(classificacao='automatica'),0) automaticas,
                coalesce(sum(classificacao='revisada'),0) revisadas,
                coalesce(sum(classificacao='pendente' AND json_extract(dados,'$.analise_ia.estado')='revisar'),0) revisar,
                coalesce(sum(classificacao='pendente' AND json_extract(dados,'$.analise_ia.estado')='incompleta'),0) incompletas,
                coalesce(sum(classificacao='pendente' AND json_extract(dados,'$.analise_ia.estado')='fora_catalogo'),0) fora_catalogo,
                coalesce(sum(revisao='pendente' AND coalesce(json_array_length(json_extract(dados,'$.analise_ia.alertas_conteudo')),0)>0),0) alertas_conteudo,
                coalesce(sum(classificacao='pendente' AND json_extract(dados,'$.analise_ia') IS NULL),0) nao_analisadas
                FROM questoes""").fetchone()
            return dict(r)

    def relatorio_ia(self, prova_id=''):
        """Diagnóstico leve; não inclui enunciados, respostas ou anotações."""
        with self.con() as c:
            sql='SELECT q.id,q.numero,q.disciplina,q.classificacao,q.revisao,q.dados,p.nome prova FROM questoes q LEFT JOIN provas p ON p.id=q.prova_id'
            args=[]
            if prova_id:sql+=' WHERE q.prova_id=?';args.append(prova_id)
            sql+=' ORDER BY p.nome,q.numero'
            out=[]
            for row in c.execute(sql,args):
                r=dict(row);a=json.loads(r.pop('dados')).get('analise_ia',{})
                r.update(estado_analise=a.get('estado','nao_analisada'),metodo=a.get('metodo',''),
                         versao_motor=a.get('versao_motor',''),motivo=a.get('motivo',''),
                         assuntos_sugeridos='; '.join(a.get('assuntos',[])),
                         alertas_conteudo='; '.join(a.get('alertas_conteudo',[])))
                out.append(r)
            return out

    def configurar(self,b):
        intervalo = int(b.get('intervalo',7))
        if intervalo not in range(7,11): raise ValueError('Escolha um intervalo de 7 a 10 dias.')
        with self.con() as c: c.execute("UPDATE meta SET valor=? WHERE chave='intervalo'",(str(intervalo),))

    def gabarito_prever(self,b):
        p = self.prova(b['prova_id'])
        entries, seen = [],set()
        for line in str(b.get('texto','')).splitlines():
            if not line.strip(): continue
            m = re.fullmatch(r'\s*(\d{1,3})\s*[;,:=\-\t ]\s*(A|B|C|D|E|X|ANULADA)\s*',line,re.I)
            if not m: raise ValueError('Formato inválido: use uma linha por questão, como 1;A. Anulada: 2;X.')
            num,key = int(m[1]),m[2].upper()
            if num in seen: raise ValueError('Número repetido no gabarito: '+str(num))
            seen.add(num)
            with self.con() as c:
                r = c.execute('SELECT id FROM questoes WHERE prova_id=? AND numero=?',(p['id'],num)).fetchone()
                if not r: raise ValueError(f'Questão {num} não encontrada nesta prova.')
                q = self._questao(c,r['id'])
            if key not in ('X','ANULADA') and key not in q.get('alternativas',{}):
                raise ValueError(f'Alternativa {key} inexistente na questão {num}; confira a extração.')
            entries.append({'id':q['id'],'numero':num,'gabarito':key,'anterior':q.get('gabarito',''), 'versao':q['versao']})
        if not entries: raise ValueError('Cole pelo menos uma linha do gabarito.')
        return {'prova':p,'itens':entries}

    def gabarito_salvar(self,b):
        if not b.get('confirmado') or not str(b.get('fonte','')).strip():
            raise ValueError('Confirme o vínculo com a prova/caderno e informe a fonte oficial.')
        preview = self.gabarito_prever(b)
        if b.get('itens') != preview['itens']:
            raise ValueError('Os dados mudaram. Gere uma nova prévia do gabarito.')
        with self.con() as c:
            for entry in preview['itens']:
                q = self._questao(c,entry['id'])
                if q['versao'] != entry['versao']: raise ValueError('A questão mudou. Gere a prévia novamente.')
                q['status_gabarito'] = 'anulada' if entry['gabarito'] in ('X','ANULADA') else 'oficial'
                q['gabarito'] = '' if q['status_gabarito']=='anulada' else entry['gabarito']
                q['fonte_gabarito'] = b['fonte']
                self._validar(q);self._gravar(c,q)
        return {'alteradas':len(preview['itens'])}

    def sessoes(self):
        with self.con() as c:
            return [dict(r) for r in c.execute('''SELECT id,nome,estado,criado,terminado,
                json_array_length(json_extract(dados,'$.questoes')) total FROM sessoes ORDER BY criado DESC''')]

    def criar_sessao(self,b):
        import random
        filtro = dict(b.get('filtro',{}));filtro['prontas'] = True
        ids = self.listar(filtro,ids=True)
        if b.get('embaralhar',True): random.SystemRandom().shuffle(ids)
        n = min(300,max(1,int(b.get('quantidade',20))))
        ids = ids[:n]
        if not ids: raise ValueError('Nenhuma questão pronta atende a esses filtros.')
        with self.con() as c:
            qs = [self._questao(c,id) for id in ids]
            id = uuid.uuid4().hex
            c.execute('INSERT INTO sessoes VALUES(?,?,?,?,?,?)',(id,str(b.get('nome') or 'Simulado')[:120],'aberta',agora(),None,dumps({'questoes':qs,'respostas':{}})))
        return self.sessao(id)

    def sessao(self,id):
        with self.con() as c:
            r = c.execute('SELECT * FROM sessoes WHERE id=?',(id,)).fetchone()
            if not r: raise ValueError('Simulado não encontrado.')
            s = dict(r);data = json.loads(s.pop('dados'))
            for q in data['questoes']:
                q.pop('ultima',None)
            data['questoes'] = [self.publicar(q,s['estado']=='concluida') for q in data['questoes']]
            s.update(data)
            if s['estado']=='concluida':
                s['resultados'] = [dict(t) for t in c.execute('SELECT * FROM tentativas WHERE sessao_id=?',(id,))]
            return s

    def responder_sessao(self,b):
        with self.con() as c:
            r = c.execute('SELECT * FROM sessoes WHERE id=?',(b['id'],)).fetchone()
            if not r or r['estado']!='aberta': raise ValueError('Este simulado não está aberto.')
            data = json.loads(r['dados'])
            q = next((q for q in data['questoes'] if q['id']==b.get('questao_id')),None)
            if not q or b.get('escolha') not in q['alternativas']: raise ValueError('Questão/alternativa inválida.')
            data['respostas'][q['id']] = {'escolha':b['escolha'],'chute':bool(b.get('chute')),'segundos':max(0,int(b.get('segundos',0)))}
            c.execute('UPDATE sessoes SET dados=? WHERE id=?',(dumps(data),b['id']))
        return {'ok':True}

    def finalizar(self,id):
        with self.con() as c:
            r = c.execute('SELECT * FROM sessoes WHERE id=?',(id,)).fetchone()
            if not r: raise ValueError('Simulado não encontrado.')
            if r['estado']=='aberta':
                data = json.loads(r['dados'])
                for q in data['questoes']:
                    if q['id'] in data['respostas']:
                        b = dict(data['respostas'][q['id']],tentativa_id=id+'-'+q['id'])
                        self._responder(c,q,b,sessao_id=id)
                c.execute("UPDATE sessoes SET estado='concluida',terminado=? WHERE id=?",(agora(),id))
        return self.sessao(id)

    def backup_sqlite(self, destino):
        with self.con() as c:
            target = sqlite3.connect(destino)
            try: c.backup(target)
            finally: target.close()
