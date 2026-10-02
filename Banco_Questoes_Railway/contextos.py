"""Contextos anteriores ao primeiro número de uma coluna; todos candidatos."""
import re
import unicodedata
import fitz


def normalizar(t):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',t.lower()) if not unicodedata.combining(c)).split())


def detectar_contextos(doc, anchors, banca):
    # Somente os perfis IBFC já inspecionados nesta etapa.
    if banca != 'IBFC':
        return []
    firsts={}
    for a in anchors:
        firsts.setdefault((a['pagina'],a['coluna']),a)
    capa=normalizar(doc[0].get_text())
    m=re.search(r'lingua portuguesa\s+(\d{1,3})\b',capa)
    limite_portugues=int(m.group(1)) if m else None
    result=[]
    for (pno,col),a in sorted(firsts.items()):
        page=doc[pno-1];w=page.rect.width
        if a['y']-2<=45:
            continue
        rect=fitz.Rect(30 if col==0 else w/2+8,45,w/2-8 if col==0 else w-30,a['y']-2)
        text=page.get_text('text',clip=rect,sort=True).strip()
        if len(text)<100:
            continue
        n=normalizar(text)
        match=re.search(r'questoes\s+(?:de\s+)?(\d{1,3})\s*(a|ate|e|-)\s*(\d{1,3})',n)
        if match:
            lo,op,hi=int(match.group(1)),match.group(2),int(match.group(3))
            if not (1<=lo<=hi<=len(anchors)):
                continue
            nums=[lo,hi] if op=='e' else list(range(lo,hi+1))
            origem='intervalo_explicito_no_pdf'
        elif a['numero']==1 and limite_portugues and 'lingua portuguesa' in n:
            nums=list(range(1,limite_portugues+1))
            origem='candidato_inferido_da_secao_e_da_contagem_na_capa'
        else:
            continue
        if a['numero'] not in nums:
            continue
        images=any(fitz.Rect(im['bbox']).intersects(rect) for im in page.get_image_info())
        result.append({'id':f'contexto-{pno}-{col+1}','numeros':nums,'criterio':origem,
                       'texto_extraido':text,'tem_imagem':images,'status':'pendente',
                       'segmentos':[{'pagina':pno,'coluna':col+1,'bbox':list(rect)}]})
    return result


def alternativas_horizontais(texto):
    # Letras podem aparecer na ordem espacial A,C,E / B,D, sem seguir A..E.
    marks=list(re.finditer(r'(?m)(?:^|[ \t]{2,})([a-e])\)[ \t]*',texto))
    letters=[m.group(1).upper() for m in marks]
    if len(letters)!=len(set(letters)) or set(letters) not in (set('ABCD'),set('ABCDE')):
        return None
    alts={}
    for i,m in enumerate(marks):
        end=marks[i+1].start() if i+1<len(marks) else len(texto)
        alts[m.group(1).upper()]=texto[m.end():end].strip()
    if any(not t for t in alts.values()):
        return None
    return texto[:marks[0].start()].strip(),dict(sorted(alts.items()))
