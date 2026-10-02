"""Perfil Cesgranrio de duas colunas, validado nas amostras UNEMAT/BANESE.
Todo resultado é candidato pendente; PDF e coordenadas são preservados.
"""
import hashlib,re,shutil
from pathlib import Path
import fitz
from contextos import normalizar


def linhas(page):
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            spans=l['spans'];t=''.join(s['text'] for s in spans).strip()
            if t:yield {'texto':t,'bbox':l['bbox'],'size':max(s['size'] for s in spans),'bold':any('Bold' in s['font'] for s in spans),'dir':l['dir']}


def eventos(doc):
    anchors=[];heads=[]
    for pn,page in enumerate(doc):
        w,h=page.rect.width,page.rect.height
        if pn==0:continue
        for l in linhas(page):
            x,y,x1,y1=l['bbox'];t=l['texto'];col=int((x+x1)/2>w/2);loc=pn*2+col
            if not 68<=y<h-65:continue
            if re.fullmatch(r'\d{1,3}',t) and l['bold'] and 9.5<=l['size']<=12 and min(abs(x-w*.0476),abs(x-w*.5238))<4:
                anchors.append(dict(numero=int(t),pagina=pn+1,coluna=col,y=y,bbox_numero=list(l['bbox']),loc=loc))
            if t.isupper() and l['size']>=10.5 and l['bold'] and re.match(r'CONHECIMENTOS|L[IÍ]NGUA|LEGISLA|HIST[OÓ]RIA|E GEOGRAFIA|[EÉ]TICA|MATEM[AÁ]TICA|NO[CÇ][OÕ]ES|ATENDIMENTO|VENDAS|ATUALIDADES|COMPORTAMENTOS|DIVERSIDADE',t):
                heads.append(dict(loc=loc,y=y,bottom=y1,texto=t))
    for a in anchors:
        page=doc[a['pagina']-1]
        nextleft=min((b['y'] for b in anchors if b['pagina']==a['pagina'] and b['coluna']==0 and b['y']>a['y']+1),default=page.rect.height-67)
        a['larga']=a['coluna']==0 and any(l['bbox'][0]<100 and l['bbox'][2]>page.rect.width*.55 and a['y']<l['bbox'][1]<nextleft for l in linhas(page))
    return sorted(anchors,key=lambda x:(x['pagina'],x['numero'])),sorted(heads,key=lambda x:(x['loc'],x['y']))


def retangulo(doc,loc,top=70,bottom=None):
    pn,col=divmod(loc,2);w,h=doc[pn].rect.width,doc[pn].rect.height
    return fitz.Rect(w*.042 if col==0 else w*.517,top,w*.487 if col==0 else w*.958,bottom if bottom is not None else h-67)


def ler(doc,loc,top=70,bottom=None,larga=False):
    rect=retangulo(doc,loc,top,bottom);pn,col=divmod(loc,2)
    if larga:rect.x1=doc[pn].rect.width*.958
    if rect.height<=0:return None
    # Não mistura colunas. Cabeçalho e rodapé ficam fora do recorte.
    rows=[];seen=set();matematica=False
    for block in doc[pn].get_text('dict',clip=rect)['blocks']:
        for line in block.get('lines',[]):
            value=''.join(s['text'] for s in line['spans'])
            key=(value,tuple(round(v,2) for v in line['bbox']))
            if key in seen:continue
            seen.add(key);rows.append((line['bbox'][1],line['bbox'][0],value))
            if any(s['flags'] & 1 or any(f in s['font'] for f in ('Euclid','Symbol','Math')) for s in line['spans']):matematica=True
    text='\n'.join(r[2] for r in sorted(rows,key=lambda r:(round(r[0]/3),r[1])))
    text='\n'.join(t for t in text.splitlines() if t.strip()!='RASCUNHO').strip()
    text=re.sub('\u00ad\\s*\\n\\s*','',text).replace('\u00ad','')
    imgs=any(fitz.Rect(im['bbox']).intersects(rect) for im in doc[pn].get_image_info())
    vectors=any(dr['rect'].intersects(rect) and dr['rect'].width>8 and dr['rect'].height>8 and dr['rect'].width<doc[pn].rect.width*.49 for dr in doc[pn].get_drawings())
    return {'texto':text,'imagem':imgs,'vetor':vectors,'matematica':matematica,'segmento':{'pagina':pn+1,'coluna':col+1,'bbox':list(rect)}}


def extrair_cesgranrio(path,destino):
    content=Path(path).read_bytes();sha=hashlib.sha256(content).hexdigest()
    with fitz.open(stream=content,filetype='pdf') as doc:
        raw,heads=eventos(doc);anchors=[];ign=[];esperado=1
        for a in raw:
            if a['numero']==esperado:anchors.append(a);esperado+=1
            else:ign.append(a)
        if not anchors:raise ValueError('Cesgranrio: nenhuma sequência reconhecida; layout diferente ou PDF sem texto. OCR não disponível.')
        capa=normalizar(doc[0].get_text());m=re.search(r'(\d{2,3})\s*(?:\([^)]*\)\s*)?questoes objetivas',capa)
        previsto=int(m.group(1)) if m else None
        if previsto and len(anchors)!=previsto:
            raise ValueError(f'Cesgranrio: extração incompleta ({len(anchors)}/{previsto}); arquivo não incorporado. É necessário revisar o layout.')
        if ign and any(a['numero']>len(anchors) for a in ign):
            raise ValueError('Cesgranrio: lacuna na numeração; revise o layout antes de importar.')
        # Textos anteriores às primeiras questões de cada seção de idioma.
        contextos=[]
        for h in heads:
            if not normalizar(h['texto']).startswith(('lingua portuguesa','lingua inglesa')):continue
            nxt=next((a for a in anchors if (a['loc'],a['y'])>(h['loc'],h['y'])),None)
            if not nxt:continue
            pedacos=[]
            for loc in range(h['loc'],nxt['loc']+1):
                part=ler(doc,loc,h['bottom']+1 if loc==h['loc'] else 70,nxt['y']-1 if loc==nxt['loc'] else None)
                if part and part['texto']:pedacos.append(part)
            if sum(len(p['texto']) for p in pedacos)<100:continue
            nexthead=next((v for v in heads if (v['loc'],v['y'])>(nxt['loc'],nxt['y'])),None)
            nums=[a['numero'] for a in anchors if (a['loc'],a['y'])>=(nxt['loc'],nxt['y']) and (not nexthead or (a['loc'],a['y'])<(nexthead['loc'],nexthead['y']))]
            contextos.append({'id':f'contexto-{h["loc"]}','numeros':nums,'criterio':'candidato_inferido_dos_limites_da_secao_de_idioma','texto_extraido':'\n\n'.join(p['texto'] for p in pedacos),'tem_imagem':any(p['imagem'] for p in pedacos),'status':'pendente','segmentos':[p['segmento'] for p in pedacos]})
        registros=[]
        for i,a in enumerate(anchors):
            nxt=anchors[i+1] if i+1<len(anchors) else None
            parts=[];flags=set()
            # Cada coluna termina na próxima questão da mesma coluna ou faixa larga.
            posteriores=[b['y']-1 for b in anchors if b['pagina']==a['pagina'] and b['y']>a['y']+1 and (a['larga'] or b['larga'] or b['coluna']==a['coluna'])]
            posteriores += [h['y']-1 for h in heads if h['loc']==a['loc'] and h['y']>a['y']+1]
            bottom=min(posteriores,default=doc[a['pagina']-1].rect.height-67)
            part=ler(doc,a['loc'],a['y']-1,bottom,a['larga'])
            if part:parts.append(part)
            texto='\n\n'.join(p['texto'] for p in parts)
            sem=re.sub(r'^\s*'+str(a['numero'])+r'\s*\n','',texto,count=1)
            marks=list(re.finditer(r'(?<![\w])\(([A-E])\)[ \t]*',sem));letras=[m.group(1) for m in marks]
            en=sem[:marks[0].start()].strip() if marks else sem;alts={}
            if letras==list('ABCDE'):
                for j,mk in enumerate(marks):alts[mk.group(1)]=sem[mk.end():marks[j+1].start() if j+1<len(marks) else len(sem)].strip()
                if any(not v for v in alts.values()):
                    flags.add('alternativa_sem_texto_verificar_imagem')
                    flags.add('cesgranrio_conteudo_visual_pendente')
            else:flags.add('marcadores_de_alternativas_incompletos_ou_ambiguos')
            if any(p['imagem'] for p in parts):flags.add('imagem_no_recorte')
            if any(p['vetor'] for p in parts):flags.add('elemento_vetorial_a_conferir')
            if re.search(r'figura|gr[aá]fico|tabela|diagrama|circuito|sublinhad|destacad',en,re.I):flags.add('conferir_texto_base_ou_formatacao_visual')
            # Frações, tabelas e desenhos não podem ser recompostos inventando texto.
            if any(p['vetor'] or p['matematica'] for p in parts):flags.add('cesgranrio_conteudo_visual_pendente')
            if re.search(r'[\x00-\x08\ufffd]',texto):flags.add('cesgranrio_conteudo_visual_pendente')
            if len(parts)>1:flags.add('questao_atravessa_coluna_ou_pagina')
            flags.add('conferir_fim_da_questao_e_cabecalhos')
            registros.append({'id':f'{sha[:16]}-{a["numero"]:03d}','prova_id':sha,'numero':a['numero'],'banca':'CESGRANRIO','arquivo_original':Path(path).name,'pagina_inicial':a['pagina'],'segmentos':[p['segmento'] for p in parts],'texto_extraido':texto,'enunciado_candidato':en,'alternativas_candidatas':alts,'contextos_candidatos':[c for c in contextos if a['numero'] in c['numeros']],'alertas':sorted(flags),'status':'pendente','observacao':''})
        (destino/'fontes').mkdir(parents=True,exist_ok=True);target=destino/'fontes'/(sha+'.pdf')
        if not target.exists():shutil.copyfile(path,target)
        prova={'id':sha,'arquivo':Path(path).name,'banca':'CESGRANRIO','paginas':len(doc),'perfil':'cesgranrio_duas_colunas_v1','questoes_previstas_capa':previsto,'questoes_detectadas':len(registros),'marcadores_ignorados':ign,'origem_oficial_verificada':False}
        return prova,registros
