"""Classificação híbrida local; conteúdo e gabarito não são alterados."""
import json
import re
import time
from pathlib import Path
from ia_comum import MODELO_DIR, MODELO_REPO, VERSAO_IA, assinatura, catalogo_ia, verificar_modelo
from regras_assuntos import normalizar, pista_comando, pistas_assuntos, PT


def alertas_conteudo(q):
    avisos=[]
    e=q.get('enunciado','');a=q.get('alternativas') or {}
    if len(e.strip())<15:avisos.append('Enunciado curto ou ausente.')
    if set(a) not in (set('AB'),set('ABCD'),set('ABCDE')) or any(not str(x).strip() for x in a.values()):
        avisos.append('Alternativas incompletas; confira o PDF.')
    if re.search(r'[\x00-\x08\x0e-\x1f\ufffd]',e+' '.join(str(x) for x in a.values())):
        avisos.append('Há símbolos ilegíveis na extração; confira o PDF.')
    if q.get('modo_visual') and q.get('revisao')!='apta':
        avisos.append('Conteúdo visual ou formatação ainda não conferidos.')
    return avisos


def motivo_incompleta(q):
    # Compatibilidade de diagnóstico: estes avisos não impedem reconhecer assunto.
    return ' '.join(alertas_conteudo(q))


def texto_limpo(s):
    return ' '.join(re.sub(r'[\x00-\x08\x0e-\x1f\ufffd]', ' ', str(s)).split())


def resumir_trecho(s,limite):
    s=texto_limpo(s)
    return s if len(s)<=limite else s[:limite//3]+' […] '+s[-(limite*2//3):]


def secoes_cesgranrio(pdf):
    """Pistas de cabeçalhos reais; seção genérica interrompe a anterior."""
    import fitz
    from cesgranrio import eventos, linhas
    resultado={}
    with fitz.open(pdf) as doc:
        anchors, heads=eventos(doc)
        for a in anchors:
            prev=[h for h in heads if (h['loc'],h['y']) < (a['loc'],a['y'])]
            if not prev:continue
            h=prev[-1]; pn,col=divmod(h['loc'],2)
            # Complementos de título quebrados em duas linhas, como "NOÇÕES
            # DE INFORMÁTICA", podem não estar no detector de eventos.
            texto=' '.join(l['texto'] for l in linhas(doc[pn]) if h['y']-1<=l['bbox'][1]<h['bottom']+21
                           and int((l['bbox'][0]+l['bbox'][2])/2>doc[pn].rect.width/2)==col
                           and l['bold'] and l['texto'].isupper())
            t=normalizar(texto or h['texto']);d='';topic=''
            if 'lingua portuguesa' in t:d='Língua Portuguesa'
            elif 'lingua inglesa' in t:d='Língua Inglesa'
            elif 'matematica financeira' in t:d='Raciocínio Lógico-Matemático';topic='Matemática financeira'
            elif 'matematica' in t or 'raciocinio logico' in t:d='Raciocínio Lógico-Matemático'
            elif 'informatica' in t:d='Informática'
            elif 'conhecimentos bancarios' in t:d='Conhecimentos Bancários'
            elif 'atendimento' in t and 'vendas' in t:d='Conhecimentos Bancários';topic='Atendimento e vendas'
            if d:resultado[a['numero']]={'disciplina':d,'assunto':topic,'evidencia':'Cabeçalho do PDF: '+(texto or h['texto'])}
    return resultado


class Classificador:
    def __init__(self,pasta=None,threads=2,usar_modelo=True):
        self.pasta=Path(pasta or MODELO_DIR);self.threads=max(1,min(16,int(threads)))
        self.usar_modelo=usar_modelo;self.session=None;self.vetores={}
        self.base,self.descricoes=catalogo_ia()
        self.opcoes=[]
        for d,temas in self.base.items():
            for a in temas:
                desc=self.descricoes['assuntos'].get(a,a)
                if d=='Língua Inglesa':desc='Compreensão, vocabulário ou gramática de texto em inglês. '+a
                self.opcoes.append((d,a,desc))
        self.opcoes.extend(('Fora do catálogo',a,desc) for a,desc in [
            ('Medicina e saúde','diagnóstico, tratamento, sintomas, doenças, anatomia e saúde clínica'),
            ('Engenharia especializada','projetos de engenharia, resistência de materiais, máquinas e instalações técnicas'),
            ('Outras especialidades','conhecimentos especializados de contabilidade, agronomia, veterinária e profissões não descritas no catálogo')])

    def carregar(self):
        if self.session is not None:return
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        verificar_modelo(self.pasta);self.np=np
        config=json.loads((self.pasta/'config.json').read_text(encoding='utf-8'))
        opts=ort.SessionOptions();opts.intra_op_num_threads=self.threads;opts.inter_op_num_threads=1
        opts.add_session_config_entry('session.intra_op.allow_spinning','0')
        opts.add_session_config_entry('session.inter_op.allow_spinning','0')
        self.session=ort.InferenceSession(str(self.pasta/'model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
        self.tk=Tokenizer.from_file(str(self.pasta/'tokenizer.json'))
        self.tk.enable_padding(pad_id=config.get('pad_token_id',1),pad_token='<pad>')
        self.tk.enable_truncation(max_length=512)

    def representar(self,textos):
        self.carregar();np=self.np;out=[]
        for i in range(0,len(textos),2):
            enc=self.tk.encode_batch(['query: '+t for t in textos[i:i+2]])
            ids=np.array([e.ids for e in enc],dtype=np.int64)
            mask=np.array([e.attention_mask for e in enc],dtype=np.int64)
            feed={'input_ids':ids,'attention_mask':mask,'token_type_ids':np.zeros_like(ids)}
            hidden=self.session.run(None,feed)[0]
            pooled=(hidden*mask[...,None]).sum(axis=1)/mask.sum(axis=1,keepdims=True)
            pooled/=np.maximum(np.linalg.norm(pooled,axis=1,keepdims=True),1e-12)
            out.extend(pooled)
        return np.asarray(out)

    def comparar(self,texto,candidatos,tema=False):
        chave=tuple(candidatos)
        if chave not in self.vetores:self.vetores[chave]=self.representar([n+'. '+d+'.' for n,d in candidatos])
        scores=self.vetores[chave]@self.representar([texto])[0]
        return sorted([{'nome':n,'similaridade':round(float(scores[i]),4)} for i,(n,_) in enumerate(candidatos)],key=lambda x:-x['similaridade'])

    def classificar(self,q,pista_pdf=None):
        inicio=time.monotonic();avisos=alertas_conteudo(q)
        result={'assinatura':assinatura(q),'versao_motor':VERSAO_IA,'modelo':MODELO_REPO if self.usar_modelo else '',
                'disciplina':'','assuntos':[],'estado':'revisar','motivo':'','candidatos':[],
                'alertas_conteudo':avisos,'nota':'Similaridades são índices do modelo, não probabilidades de acerto.'}
        def fim(**kw):return dict(result,segundos=round(time.monotonic()-inicio,2),**kw)
        e=texto_limpo(q.get('enunciado',''))
        if len(re.findall(r'[A-Za-zÀ-ÿ]{2,}',e))<4:
            return fim(estado='incompleta',codigo_motivo='texto_insuficiente',motivo='O enunciado não contém texto suficiente para reconhecer o assunto. Confira o PDF.')
        pistas=pistas_assuntos(q)
        # Pergunta de compreensão textual explícita, sem usar o tema da notícia.
        if not pistas:
            t=normalizar(re.sub(r'“[^”]*”|"[^\"]*"',' ',e))
            idioma=PT if not pista_pdf else pista_pdf.get('disciplina')
            if idioma==PT and not re.search(r'refere-se|retoma|substituid|concordancia|regencia',t) and re.search(r'(?:de acordo|segundo).{0,40}(?:o texto|o autor)|desenvolvimento tematico|ordem das ideias|funcao.{0,25}(?:texto|citacao)|citacao.{0,100}funcao|objetivo (?:principal )?do texto|ideia (?:central|principal) do texto',t):
                pistas=[{'disciplina':PT,'assunto':'Interpretação de textos','evidencia':'O comando pede compreensão, finalidade ou organização de ideias do texto.'}]
        # Uma seção em língua estrangeira não pode receber tag por palavra em português.
        conflito_idioma=bool(pista_pdf and pista_pdf['disciplina'] in (PT,'Língua Inglesa') and pistas and any(x['disciplina']!=pista_pdf['disciplina'] for x in pistas))
        # Um cabeçalho específico pode desempatar conhecimentos explicitamente
        # presentes (por exemplo, juros e progressões no mesmo financiamento).
        if pista_pdf and pista_pdf.get('assunto'):
            coincidem=[p for p in pistas if (p['disciplina'],p['assunto'])==(pista_pdf['disciplina'],pista_pdf['assunto'])]
            if coincidem and all(p['disciplina']==pista_pdf['disciplina'] for p in pistas):
                pistas=coincidem
        if len(pistas)==1 and not conflito_idioma:
            p=pistas[0]
            return fim(disciplina=p['disciplina'],assuntos=[p['assunto']],estado='automatica',
                       metodo='comando_explicito',codigo_motivo='pista_explicita',motivo=p['evidencia'])
        if not self.usar_modelo:
            if pistas:
                p=pistas[0]
                cs=[{'nome':x['assunto'],'disciplina':x['disciplina'],'evidencia':x['evidencia']} for x in pistas[:5]]
                return fim(disciplina=p['disciplina'],assuntos=[p['assunto']],candidatos=cs,metodo='regras',codigo_motivo='pistas_concorrentes',motivo='Há pistas de mais de um assunto. Confira ou execute com o modelo local.')
            return fim(metodo='regras',codigo_motivo='sem_pista',motivo='Sem pista explícita suficiente. O modelo local pode propor assuntos.')
        # Duas visões limitadas separadamente: o comando final não é descartado
        # em questões longas e as alternativas chegam ao segundo embedding.
        comando=resumir_trecho(e,1700)
        alts=' '.join(k+') '+resumir_trecho(v,190) for k,v in (q.get('alternativas') or {}).items())
        completo=resumir_trecho(e,900)+' Alternativas: '+alts
        if len(e)<180 and q.get('contexto'):
            completo+=' Contexto: '+resumir_trecho(q['contexto'],350)
        if 'catalogo' not in self.vetores:
            self.vetores['catalogo']=self.representar([d+'. '+a+'. '+desc for d,a,desc in self.opcoes])
        v=self.representar([comando,completo]);scores=self.vetores['catalogo']@v.T
        media=.65*scores[:,0]+.35*scores[:,1]
        # Cabeçalho é evidência adicional. Nunca é requisito para classificar.
        ajustado=media.copy()
        if pista_pdf:
            for i,(d,a,_) in enumerate(self.opcoes):
                if d==pista_pdf['disciplina']:ajustado[i]+=.008
        ordem=ajustado.argsort()[::-1]
        top=int(ordem[0]);d,a,_=self.opcoes[top]
        gap=float(ajustado[top]-ajustado[int(ordem[1])])
        consenso=int(scores[:,0].argmax())==int(scores[:,1].argmax())==top
        cs=[{'disciplina':self.opcoes[int(i)][0],'nome':self.opcoes[int(i)][1],
             'similaridade':round(float(media[int(i)]),4)} for i in ordem[:5]]
        evidencias=[p for p in pistas if (p['disciplina'],p['assunto'])==(d,a)]
        # Não reduz o problema a aceitar qualquer resultado: exige margem,
        # concordância e ausência de conflito entre disciplina e pistas explícitas.
        conflito=bool(pistas and not evidencias)
        # Em uma prova com cabeçalho reconhecido, a seção é uma evidência
        # adicional. Em FGV/IBFC, onde não há esse cabeçalho, o modelo precisa
        # de uma margem maior para não transformar semelhança temática em tag.
        margem_minima = .012 if pista_pdf else .025
        nota_minima = .85 if pista_pdf else .87
        auto=bool(not conflito_idioma and not conflito and consenso and float(media[top])>=nota_minima and gap>=margem_minima)
        if evidencias and not conflito_idioma:
            auto=bool(consenso and gap>=.006 and float(media[top])>=.83)
        if d=='Fora do catálogo':
            return fim(estado='fora_catalogo' if consenso and gap>=.015 else 'revisar',codigo_motivo='fora_catalogo',metodo='modelo_local',
                       motivo='O modelo sugere uma especialidade ainda não coberta pelo catálogo. Nenhum assunto foi aplicado.',candidatos=cs)
        razao='consenso_com_margem' if auto else ('pistas_concorrentes' if conflito or conflito_idioma else 'leituras_divergentes' if not consenso else 'margem_pequena')
        motivo=('Duas leituras concordaram e houve separação entre os assuntos candidatos.' if auto else
                {'pistas_concorrentes':'As pistas do enunciado, cabeçalho ou modelo não concordaram.',
                 'leituras_divergentes':'A leitura do comando e a leitura com alternativas sugeriram assuntos diferentes.',
                 'margem_pequena':'Os assuntos candidatos ficaram próximos ou a semelhança foi insuficiente.'}[razao])
        if evidencias:motivo+=' '+evidencias[0]['evidencia']
        return fim(disciplina=d,assuntos=[a],estado='automatica' if auto else 'revisar',metodo='modelo_local',
                   codigo_motivo=razao,motivo=motivo,candidatos=cs,margem=round(gap,4),consenso=consenso,
                   segunda_leitura=[{'disciplina':self.opcoes[int(i)][0],'nome':self.opcoes[int(i)][1],
                   'similaridade':round(float(scores[int(i),1]),4)} for i in scores[:,1].argsort()[::-1][:3]])


def worker():
    """JSONL em stdin/stdout. Executado fora do servidor para liberar RAM."""
    import sys
    import os
    os.environ['TOKENIZERS_PARALLELISM']='false'
    os.environ['HF_HUB_OFFLINE']='1'
    if os.name=='nt':
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x00004000)
    else:
        try:os.nice(5)
        except OSError:pass
    args=json.loads(sys.stdin.readline())
    modelo=Classificador(args.get('pasta'),args.get('threads',2),usar_modelo=args.get('usar_modelo',True))
    if modelo.usar_modelo:modelo.carregar()
    print(json.dumps({'pronto':True}),flush=True)
    for linha in sys.stdin:
        q=json.loads(linha)
        try: r=modelo.classificar(q['questao'],q.get('pista_pdf'))
        except Exception as exc:r={'erro':str(exc)}
        print(json.dumps(r,ensure_ascii=False),flush=True)


if __name__=='__main__':
    worker()
