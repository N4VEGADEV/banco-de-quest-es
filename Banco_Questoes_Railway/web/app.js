'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const h = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n||0).toLocaleString('pt-BR');
const datefmt = s => s ? new Date(s).toLocaleString('pt-BR') : '—';
const labels = {painel:'Visão geral',questoes:'Questões',cadernos:'Cadernos',simulados:'Simulados',historico:'Histórico',importar:'Provas e importação',ia:'Classificação',config:'Dados e backup'};
const state = {view:'painel',info:null,filter:{prontas:true,pagina:1},selected:new Set(),all:false,list:null,question:null,session:null,index:0,edit:null,keyPreview:null,started:0,attempt:null,busy:false};
let toastTimer, jobTimer, iaTimer;

async function api(path,body,method){
  const options = {method:method || (body===undefined?'GET':'POST'),headers:{'X-Local-Token':state.info?.token||''}};
  if(body!==undefined){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
  const response = await fetch('/api/'+path,options);
  if(response.status===401){window.location.assign('/login');throw new Error('Sua sessão terminou. Entre novamente.');}
  const data = await response.json();
  if(!response.ok) throw new Error(data.erro||'Não foi possível concluir.');
  return data;
}
function toast(message,error=false){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').className='toast'+(error?' error':'');toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),error?10000:4500);}
function heading(title,subtitle,actions=''){return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${actions}</div></div>`;}
function empty(title,text,button=''){return `<div class="empty"><div class="empty-icon">▤</div><h3>${title}</h3><p>${text}</p>${button}</div>`;}
function button(text,action,extra='',cls=''){return `<button class="${cls}" data-action="${action}" ${extra}>${text}</button>`;}
function opt(values,current,placeholder='Todos'){return `<option value="">${placeholder}</option>`+values.map(v=>{const val=typeof v==='object'?v.value:v;const label=typeof v==='object'?v.label:v;return `<option value="${h(val)}" ${String(current||'')===String(val)?'selected':''}>${h(label)}</option>`;}).join('');}
function ready(q){return q.revisao==='apta'&&['revisada','automatica'].includes(q.classificacao);}
function reviewBadge(q){const origem=q.classificacao==='automatica'?'<span class="pill">Classificação automática</span>':'';return origem+(ready(q)?'<span class="pill green">Pronta</span>':q.revisao==='retida'?'<span class="pill red">Retida</span>':'<span class="pill amber">'+(q.revisao!=='apta'?'Conferir conteúdo':'Classificar assunto')+'</span>');}
function keyBadge(q){return `<span class="pill ${q.status_gabarito==='oficial'?'green':'amber'}">${({oficial:'Gabarito oficial',sem:'Sem gabarito',informado:'Gabarito informado',anulada:'Anulada'})[q.status_gabarito]||'Sem gabarito'}</span>`;}
function resultLabel(t){return t.correta===null||t.correta===undefined?'<span class="pill amber">Sem correção oficial</span>':t.correta?'<span class="pill green">Acertou</span>':'<span class="pill red">Errou</span>';}
function renderError(e){toast(e.message,true);}
async function refresh(){state.info=await api('inicio');if($('#account-name'))$('#account-name').textContent='Administrador: '+(state.info.usuario||'');if(state.filter.caderno_id&&!state.info.cadernos.some(c=>c.id===state.filter.caderno_id))delete state.filter.caderno_id;$('#version').textContent='Versão '+state.info.versao;$('#disciplinas').innerHTML=Object.keys(state.info.catalogo).map(d=>`<option value="${h(d)}">`).join('');}
function selectedPayload(){return state.all?{filtro:state.filter,esperado:state.list.total}:{ids:[...state.selected]};}
function selectionCount(){return state.all?state.list?.total||0:state.selected.size;}
function clearSelection(){state.selected.clear();state.all=false;}

async function nav(view){
  state.view=view;state.session=null;state.question=null;window.scrollTo(0,0);
  $('#breadcrumb').textContent='Meu espaço / '+(labels[view]||'Questões');
  $$('.sidebar nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $('#content').innerHTML='<div class="loading">Carregando…</div>';
  try{
    if(view==='painel')await dashboard();
    else if(view==='questoes')await questions();
    else if(view==='cadernos')await books();
    else if(view==='simulados')await sessions();
    else if(view==='historico')await history();
    else if(view==='importar')await imports();
    else if(view==='ia')await classification();
    else if(view==='config')await settings();
  }catch(e){$('#content').innerHTML=empty('Não foi possível carregar',h(e.message),button('Tentar novamente','reload'));renderError(e);}
}

async function dashboard(){
  const p=await api('painel'),q=p.questoes,t=p.resultados;
  const rate=t.corrigidas?Math.round(t.acertos/t.corrigidas*100)+'%':'—';
  $('#content').innerHTML=heading('Seu espaço de estudo','Questões reais, assuntos organizados e um passo de cada vez.',button('Importar provas','nav-importar','','primary'))+
  `<div class="hero"><div><div class="eyebrow">PRÁTICA COM FOCO</div><h2>${q.prontas?'Seu próximo treino começa aqui.':'Vamos organizar seu primeiro treino.'}</h2><p>${q.prontas?`${fmt(q.prontas)} ${q.prontas===1?'questão conferida e classificada espera':'questões conferidas e classificadas esperam'} por você. Escolha um assunto e comece.`:'Importe uma prova, confira o conteúdo e registre os assuntos. Depois, encontre suas questões pelos filtros.'}</p>${button(q.prontas?'Explorar questões →':'Adicionar PDFs →',q.prontas?'nav-questoes':'nav-importar')}</div><div class="hero-mark" aria-hidden="true">q.</div></div>
  <div class="stats-grid">${[
    ['Questões no acervo',fmt(q.total),fmt(q.prontas)+(q.prontas===1?' pronta para resolver':' prontas para resolver')],['Questões respondidas',fmt(t.respondidas),fmt(t.tentativas)+' tentativas registradas'],['Aproveitamento',rate,fmt(t.corrigidas)+' tentativas com gabarito oficial'],['Revisão disponível',fmt(q.revisar),'Erros, chutes e revisões agendadas']
  ].map(x=>`<div class="stat"><div class="label">${x[0]}</div><span class="value">${x[1]}</span><span class="foot">${x[2]}</span></div>`).join('')}</div>
  <div class="two-col"><section class="panel"><div class="row"><h2>Seu desempenho por disciplina</h2><span class="pill">Todas as tentativas</span></div>${p.disciplinas.length?p.disciplinas.map(d=>`<div class="divide"><div class="row"><strong>${h(d.disciplina)}</strong><span>${d.corrigidas?Math.round(d.acertos/d.corrigidas*100)+'%':'—'}</span></div><div class="progress-track"><progress max="100" value="${d.corrigidas?d.acertos/d.corrigidas*100:0}"></progress></div><span class="subtle">${d.acertos} acertos em ${d.corrigidas} tentativas corrigidas · ${d.tentativas} tentativas ao todo</span></div>`).join(''):empty('Seu progresso aparecerá aqui','Responda questões com gabarito oficial para acompanhar seus resultados.')}</section>
  <section class="panel"><h2>Organização do acervo</h2><div class="divide row"><span>Conteúdo para conferir</span><strong>${fmt(q.pendentes)}</strong></div><div class="divide row"><span>Classificações pendentes</span><strong>${fmt(q.sem_classificacao)}</strong></div><div class="divide row"><span>Questões retidas</span><strong>${fmt(q.retidas)}</strong></div><p class="subtle spacer-top">As contagens podem se sobrepor: uma questão pode precisar das duas conferências.</p><div class="actions">${button('Classificar com IA local','nav-ia')+button('Conferir questões','review-list')}${button('Revisar erros e chutes','due-list','','ghost')}</div></section></div>
  ${t.sem_gabarito?`<div class="notice">${fmt(t.sem_gabarito)} tentativa(s) sem correção oficial estão registradas, mas não entram no aproveitamento.</div>`:''}`;
}

function filterForm(){
  const f=state.filter,exams=state.info.provas,cat=state.info.catalogo;
  const temas=f.disciplina?cat[f.disciplina]||[]:[...new Set(Object.values(cat).flat())].sort();
  return `<form id="filters" class="panel"><div class="filter-grid">
  <label>Disciplina<select name="disciplina">${opt(Object.keys(cat),f.disciplina)}</select></label>
  <label>Assunto e subassuntos<select name="assunto">${opt(temas,f.assunto)}</select></label>
  <label>Banca<select name="banca">${opt([...new Set(exams.map(p=>p.banca).filter(Boolean))].sort(),f.banca)}</select></label>
  <label>Ano<select name="ano">${opt([...new Set(exams.map(p=>p.ano).filter(Boolean))].sort().reverse(),f.ano)}</select></label>
  <label>Prova<select name="prova_id">${opt(exams.map(p=>({value:p.id,label:p.nome})),f.prova_id)}</select></label>
  <label>Minhas respostas<select name="situacao">${opt([{value:'nao',label:'Não respondidas'},{value:'respondidas',label:'Respondidas'},{value:'certas',label:'Última resposta certa'},{value:'erradas',label:'Última resposta errada'},{value:'chutes',label:'Última resposta com chute'},{value:'pendentes',label:'Respondidas sem correção'},{value:'revisar',label:'Revisão disponível hoje'}],f.situacao)}</select></label>
  <label>Gabarito<select name="gabarito">${opt([{value:'oficial',label:'Oficial cadastrado'},{value:'sem',label:'Sem gabarito'},{value:'informado',label:'Informado / não oficial'},{value:'anulada',label:'Anulada'}],f.gabarito)}</select></label>
  <label>Buscar no texto<input name="texto" value="${h(f.texto||'')}" placeholder="Palavra ou expressão"></label>
  <label>Conferência do conteúdo<select name="revisao">${opt([{value:'pendente',label:'Pendente'},{value:'apta',label:'Conferida'},{value:'retida',label:'Retida'}],f.revisao)}</select></label>
  <label>Classificação<select name="classificacao">${opt([{value:'pendente',label:'Pendente'},{value:'revisada',label:'Revisada por você'},{value:'automatica',label:'Classificada automaticamente'}],f.classificacao)}</select></label>
  <label>Análise local<select name="ia">${opt([{value:'revisar',label:'Sugestões para conferir'},{value:'incompleta',label:'Texto insuficiente para classificar'},{value:'fora_catalogo',label:'Especialidade fora do catálogo'},{value:'alertas_conteudo',label:'Avisos de conteúdo pendentes'},{value:'sem',label:'Ainda não analisadas'}],f.ia)}</select></label>
  <label>Caderno<select name="caderno_id">${opt(state.info.cadernos.map(c=>({value:c.id,label:c.nome})),f.caderno_id)}</select></label>
  <label>Ordenação<select name="ordem">${opt([{value:'recentes',label:'Alteradas recentemente'}],f.ordem,'Prova e número')}</select></label>
  </div><div class="filter-bottom"><div class="checks"><label class="check"><input type="checkbox" name="prontas" ${f.prontas?'checked':''}>Só prontas para resolver</label><label class="check"><input type="checkbox" name="favoritos" ${f.favoritos?'checked':''}>Favoritas</label><label class="check"><input type="checkbox" name="evitar_recentes" ${f.evitar_recentes?'checked':''}>Respeitar intervalo de revisão</label></div><div class="actions">${button('Limpar','clear-filters','','ghost')}<button type="submit" class="primary">Filtrar questões</button></div></div></form>`;
}

async function questions(){
  await refresh();state.list=await api('questoes?filtro='+encodeURIComponent(JSON.stringify(state.filter)));
  const list=state.list;
  $('#content').innerHTML=heading('Banco de questões','Filtre pelos assuntos cadastrados. Corrija uma classificação uma vez e aproveite nas próximas sessões.',button('Criar simulado','new-session')+button('Cadastrar pelo PDF','new-question'))+
  filterForm()+`<div class="toolbar"><div><strong>${fmt(list.total)} questões</strong> <span class="muted">encontradas</span></div><div class="actions"><label class="check"><input id="select-page" type="checkbox" ${list.itens.length&&list.itens.every(q=>state.all||state.selected.has(q.id))?'checked':''}>Selecionar esta página</label>${button('Selecionar todo o filtro','select-all',list.total?'':'disabled','small')}${button('Exportar JSON','export','','small ghost')}</div></div>
  <div id="selection"></div>
  <div id="question-list">${list.itens.length?list.itens.map(q=>`<article class="question-card"><div class="question-meta"><input type="checkbox" aria-label="Selecionar questão ${q.numero}" data-select="${q.id}" ${state.all||state.selected.has(q.id)?'checked':''}><span class="qnumber">Q${q.numero}</span><span>${h(q.banca||'Banca não cadastrada')} · ${h(q.ano||'Ano não cadastrado')}</span><span>${h(q.prova)}</span></div><div class="tags">${reviewBadge(q)}${keyBadge(q)}${q.tentativa?resultLabel(q):''}${q.chute?'<span class="pill amber">Chute</span>':''}</div><p class="question-title">${h((q.enunciado||'Conteúdo pendente de cadastro.').slice(0,240))}${q.enunciado?.length>240?'…':''}</p><div class="question-foot"><div class="tags">${q.disciplina?`<span class="pill">${h(q.disciplina)}</span>`:''}${q.assuntos.slice(0,2).map(a=>`<span class="pill">${h(a)}</span>`).join('')}${q.assuntos.length>2?`<span class="pill">+${q.assuntos.length-2}</span>`:''}</div><div class="actions">${button(q.favorito?'★':'☆','favorite',`data-id="${q.id}" data-value="${q.favorito?0:1}" aria-label="${q.favorito?'Remover dos':'Adicionar aos'} favoritos"`,'ghost')}${button('Conferir / editar','edit',`data-id="${q.id}"`,'small')}${button('Responder','study',`data-id="${q.id}" ${ready(q)?'':'disabled'}`,'primary small')}</div></div></article>`).join(''):empty('Nenhuma questão neste filtro','Verifique os critérios. Questões recém-importadas aparecem ao desmarcar “Só prontas para resolver”.',button('Ver todo o acervo','review-list'))}</div>
  ${list.total?`<div class="pagination">${button('← Anterior','page-prev',list.pagina<=1?'disabled':'')}<span class="muted">Página ${list.pagina} de ${Math.max(1,Math.ceil(list.total/list.limite))}</span>${button('Próxima →','page-next',list.pagina*list.limite>=list.total?'disabled':'')}</div>`:''}`;
  selectionBar();
}
function selectionBar(){const el=$('#selection');if(!el)return;const n=selectionCount();el.innerHTML=n?`<div class="selection-bar"><strong>${fmt(n)} selecionadas${state.all?' em todas as páginas':''}</strong>${button('Classificar / conferir em lote','bulk','','small')}${button('Adicionar a caderno','book-add','','small')}${state.filter.caderno_id?button('Retirar do caderno','book-remove','','small'):''}${button('Limpar seleção','deselect','','small ghost')}</div>`:'';}
function readFilter(){const f=Object.fromEntries(new FormData($('#filters')));for(const k of ['prontas','favoritos','evitar_recentes'])f[k]=Boolean(f[k]);f.pagina=1;return f;}

function showModal(title,body,footer=''){const dialog=$('#modal');$('#modal-content').innerHTML=`<div class="modal-head"><h2>${title}</h2>${button('✕','close-modal','aria-label="Fechar"','ghost')}</div><div class="modal-body">${body}</div>${footer?'<div class="modal-footer">'+footer+'</div>':''}`;if(!dialog.open)dialog.showModal();}
function sourceImages(q){return ['contexto','questao'].map(tipo=>{const segs=q[tipo==='contexto'?'segmentos_contexto':'segmentos']||[];return segs.map((s,i)=>`<figure><figcaption class="subtle">${tipo==='contexto'?'Texto-base':'Questão'} · página ${s.pagina}</figcaption><img class="image-source" alt="Recorte original ${tipo}, página ${s.pagina}" loading="lazy" src="/api/imagem?id=${encodeURIComponent(q.id)}&tipo=${tipo}&indice=${i}${state.session?'&sessao='+state.session.id:''}"></figure>`).join('');}).join('');}
function pdfLink(q){return q.prova_id?`<a class="btn-link" href="/pdf/${h(q.prova_id)}.pdf#page=${q.segmentos?.[0]?.pagina||1}" target="_blank" rel="noopener">Abrir PDF original ↗</a>`:'';}

function analysisBox(q){
  const a=q.analise_ia;if(!a)return '';
  const itens=[...(a.assuntos||[]).map(n=>({nome:n,disciplina:a.disciplina})),...(a.candidatos||[])];
  const seen=new Set(),opcoes=itens.filter(c=>{const key=(c.disciplina||a.disciplina)+'|'+c.nome;if(seen.has(key)||!c.nome||c.disciplina==='Fora do catálogo')return false;seen.add(key);return true;}).slice(0,4);
  return `<section class="details-box"><h3>Análise de assunto</h3><p class="small-text">${h(a.motivo)}</p><p class="subtle">${a.metodo==='api_claude'?'Claude por API · '+h(a.modelo||''):a.metodo==='modelo_local'?'Comparação semântica local':a.metodo==='comando_explicito'?'Pista explícita no enunciado':'Análise local'} · ${h(a.versao_motor||'')}</p>${a.evidencia?`<p class="small-text">Evidência: “${h(a.evidencia)}”</p>`:''}${opcoes.map(c=>`<div class="divide"><strong class="small-text">${h(c.nome)}</strong><p class="subtle">${h(c.disciplina||a.disciplina||'')}</p><div>${button('Usar este assunto','ia-use',`data-topic="${h(c.nome)}" data-discipline="${h(c.disciplina||a.disciplina||'')}"`,'small ghost')}</div></div>`).join('')}${a.alertas_conteudo?.length?`<div class="notice spacer-top"><strong>Conferência do conteúdo</strong><ul>${a.alertas_conteudo.map(t=>`<li>${h(t)}</li>`).join('')}</ul><p class="small-text">O assunto pode ser identificado mesmo com estes avisos. Confira o original antes de liberar a resolução.</p></div>`:''}<p class="subtle">A análise não confirma o conteúdo nem o gabarito. Ao usar uma sugestão e salvar, você confirma a classificação.</p></section>`;
}

async function edit(id){
  const q=id?await api('questao?id='+encodeURIComponent(id)+'&editar=1'):{enunciado:'',alternativas:{A:'',B:'',C:'',D:'',E:''},assuntos:[],contexto:'',revisao:'pendente',classificacao:'pendente',status_gabarito:'sem',segmentos:[],segmentos_contexto:[],prova_id:state.filter.prova_id||state.info.provas[0]?.id||'',numero:''};
  state.edit=q;
  const temas=state.info.catalogo[q.disciplina]||[];
  const body=`<div class="editor-grid"><form id="edit-form" class="form-stack">${analysisBox(q)}
  ${!id?`<div class="form-grid"><label>Prova<select name="prova_id" required>${opt(state.info.provas.map(p=>({value:p.id,label:p.nome})),q.prova_id,'Escolha a prova')}</select></label><label>Número da questão<input name="numero" type="number" min="1" required></label></div>`:`<div class="muted small-text">Q${q.numero} · ${h(q.prova.nome)}<br>Alterações ficam nesta versão local. O PDF original é preservado.</div>`}
  <label>Enunciado<textarea name="enunciado" rows="5" required>${h(q.enunciado)}</textarea></label>
  <details class="details-box" ${q.contexto?'open':''}><summary>Texto-base associado</summary><textarea name="contexto" rows="7" placeholder="Inclua o texto necessário para resolver esta questão.">${h(q.contexto)}</textarea></details>
  ${['A','B','C','D','E'].map(k=>`<label>Alternativa ${k}<textarea name="alt_${k}" rows="2" placeholder="${k==='C'?'Para Certo/Errado use apenas A e B.':k==='E'?'Deixe vazia se a prova tiver quatro alternativas.':''}">${h(q.alternativas?.[k]||'')}</textarea></label>`).join('')}
  <div class="form-grid"><label>Disciplina<input name="disciplina" list="disciplinas" value="${h(q.disciplina||'')}" placeholder="Selecione ou escreva"></label><label>Classificação<select name="classificacao">${opt([{value:'pendente',label:'Pendente de revisão'},{value:'revisada',label:'Revisada por você'},...(q.classificacao==='automatica'?[{value:'automatica',label:'Classificada automaticamente'}]:[])],q.classificacao,'Selecione')}</select></label></div>
  <label>Adicionar assunto do catálogo<select id="edit-topic">${opt(temas,'','Escolha um assunto para adicionar')}</select></label>
  <label>Assuntos da questão<textarea name="assuntos" rows="3" placeholder="Separe por ponto e vírgula. Use / para criar subassuntos.">${h(q.assuntos.join('; '))}</textarea></label>
  <p class="subtle">Classifique o conhecimento cobrado. Um termo presente só no texto ou em uma alternativa não basta. Você pode criar novos assuntos.</p>
  <label>Conferência do conteúdo<select name="revisao">${opt([{value:'pendente',label:'Pendente'},{value:'apta',label:'Completa e conferida'},{value:'retida',label:'Retida para correção'}],q.revisao,'Selecione')}</select></label>
  <label class="check check-box"><input name="conferida" type="checkbox" ${q.conferida?'checked':''}>Conferi no PDF o enunciado, as alternativas, o texto-base e os elementos visuais necessários.</label>
  <label class="check"><input name="modo_visual" type="checkbox" ${q.modo_visual?'checked':''}>Exibir recortes originais ao abrir a questão.</label>
  <details class="details-box"><summary>Gabarito e explicação</summary><div class="form-grid"><label>Situação<select name="status_gabarito">${opt([{value:'sem',label:'Sem gabarito'},{value:'oficial',label:'Oficial conferido'},{value:'informado',label:'Informado, não oficial'},{value:'anulada',label:'Anulada'}],q.status_gabarito)}</select></label><label>Alternativa correta<select name="gabarito">${opt(['A','B','C','D','E'],q.gabarito,'Sem resposta')}</select></label><label class="span-2">Fonte do gabarito<input name="fonte_gabarito" value="${h(q.fonte_gabarito||'')}" placeholder="Documento, endereço e identificação do caderno"></label><label class="span-2">Explicação / comentário de resolução<textarea name="explicacao" rows="4">${h(q.explicacao||'')}</textarea></label></div><p class="subtle spacer-top">Marque “Oficial” somente após conferir a fonte e o tipo de prova. A explicação cadastrada não é validada automaticamente.</p></details>
  <details class="details-box" ${!id?'open':''}><summary>Incluir páginas do PDF</summary><div class="form-grid"><label>Páginas inteiras da questão<input name="paginas_questao" placeholder="Ex.: 3 ou 3, 4"></label><label>Páginas extras do texto-base<input name="paginas_contexto" placeholder="Ex.: 2"></label></div><p class="subtle spacer-top">Adiciona as páginas indicadas aos recortes existentes. Use quando o recorte não contiver toda a questão ou seu contexto.</p></details>
  <details class="details-box"><summary>Avisos da extração (${q.alertas?.length||0})</summary><ul class="help-list">${(q.alertas||[]).map(a=>`<li>${h(a.replaceAll('_',' '))}</li>`).join('')}</ul><p class="subtle">São sinais para conferência, não uma classificação automática de qualidade.</p></details>
  </form><div><div class="editor-preview"><div class="row"><h3>Referência original</h3>${pdfLink(q)}</div>${id?sourceImages(q):'<p class="muted">Abra o PDF da prova escolhida e informe a página da questão. O conteúdo pode ser cadastrado mesmo quando o layout não tem extração automática.</p>'}${!q.segmentos?.length&&id?'<p class="muted">Sem recortes associados. Use o PDF completo.</p>':''}</div></div></div>`;
  showModal(id?'Conferir e classificar · Q'+q.numero:'Cadastrar questão de uma prova',body,`<span id="edit-status" class="muted small-text">O filtro utiliza os assuntos que você registrar.</span><div class="actions">${button('Cancelar','close-modal')}<button type="submit" form="edit-form" class="primary">Salvar questão</button>${id&&state.view==='questoes'?'<button type="submit" form="edit-form" name="proxima" value="1">Salvar e próxima →</button>':''}</div>`);
}

function pages(input){if(!input.trim())return [];const nums=input.split(/[,;\s]+/).filter(Boolean).map(Number);if(nums.some(n=>!Number.isInteger(n)||n<1||n>3000))throw new Error('Informe números de página válidos.');return [...new Set(nums)].map(n=>({pagina:n,coluna:1,bbox:[0,0,2000,2000]}));}
async function saveEdit(proxima=false){
  const f=Object.fromEntries(new FormData($('#edit-form'))),q=state.edit;
  const alternatives={};for(const k of ['A','B','C','D','E'])if(f['alt_'+k]?.trim())alternatives[k]=f['alt_'+k].trim();
  const body={id:q.id,versao:q.versao,prova_id:f.prova_id||q.prova_id,numero:f.numero||q.numero,enunciado:f.enunciado,alternativas:alternatives,contexto:f.contexto,disciplina:f.disciplina.trim(),assuntos:f.assuntos.split(';').map(s=>s.trim()).filter(Boolean),revisao:f.revisao,classificacao:f.classificacao,conferida:!!f.conferida,modo_visual:!!f.modo_visual,gabarito:f.gabarito,status_gabarito:f.status_gabarito,fonte_gabarito:f.fonte_gabarito,explicacao:f.explicacao,segmentos:[...(q.segmentos||[]),...pages(f.paginas_questao||'')],segmentos_contexto:[...(q.segmentos_contexto||[]),...pages(f.paginas_contexto||'')]};
  const ids=(state.list?.itens||[]).map(x=>x.id),idx=ids.indexOf(q.id),next=idx>=0?ids[idx+1]:null;
  await api('questao',body);$('#modal').close();toast('Questão salva.');clearSelection();await nav(state.view);
  if(proxima&&next)await edit(next);else if(proxima)toast('Página conferida. Avance a lista para continuar.');
}

function bulk(){
  showModal('Organizar '+fmt(selectionCount())+' questões',`<form id="bulk-form" class="form-stack modal-narrow"><div class="notice">A alteração será aplicada a todas as questões selecionadas${state.all?', inclusive às outras páginas':''}. Use o mesmo assunto apenas se ele for cobrado por todas.</div><label>Disciplina<input name="disciplina" list="disciplinas" placeholder="Em branco preserva a atual"></label><label>Assuntos<textarea name="assuntos" placeholder="Separe por ponto e vírgula. Em branco preserva os atuais."></textarea></label><label class="check"><input type="checkbox" name="substituir">Substituir assuntos existentes pelos informados</label><label>Classificação<select name="classificacao">${opt([{value:'revisada',label:'Marcar como revisada'},{value:'pendente',label:'Marcar como pendente'}],'','Manter atual')}</select></label><label>Conferência do conteúdo<select name="revisao">${opt([{value:'apta',label:'Marcar como completa e conferida'},{value:'pendente',label:'Marcar como pendente'},{value:'retida',label:'Reter para correção'}],'','Manter atual')}</select></label><label class="check check-box"><input type="checkbox" name="conferida">Conferi o conteúdo completo de todas as questões que estou liberando.</label><p class="subtle">Se alguma questão não passar pela validação, o lote inteiro permanece como estava.</p></form>`,`${button('Cancelar','close-modal')}<button type="submit" form="bulk-form" class="primary">Aplicar ao lote</button>`);
}

async function study(id){
  state.question=await api('questao?id='+encodeURIComponent(id));state.session=null;state.started=Date.now();state.attempt=crypto.randomUUID();
  $('#breadcrumb').textContent='Meu espaço / Resolução';renderStudy();window.scrollTo(0,0);
}
function renderStudy(feedback){
  const session=state.session;const q=session?session.questoes[state.index]:state.question;
  if(!q)return;
  const completed=session?.estado==='concluida';const answer=session?.respostas[q.id];
  const result=completed?session.resultados.find(t=>t.questao_id===q.id):feedback?.tentativa;
  const reveal=feedback?.questao||(completed?q:null);
  const choice=result?.escolha||answer?.escolha||'';
  $('#content').innerHTML=heading(session?session.nome:'Resolver questão',session?`Questão ${state.index+1} de ${session.questoes.length} · ${completed?'simulado finalizado':'respostas salvas ao avançar'}`:`${h(q.prova.banca||'Banca não cadastrada')} · ${h(q.prova.ano||'')} · ${h(q.prova.nome)}`,button(session?'Voltar aos simulados':'Voltar às questões',session?'nav-simulados':'nav-questoes'))+
  `<div class="study-layout"><section class="panel study-main"><div class="row"><div class="tags"><span class="pill">Q${q.numero}</span>${keyBadge(q)}${q.classificacao==='automatica'?'<span class="pill">Classificação automática</span>':''}${q.assuntos.map(a=>`<span class="pill">${h(a)}</span>`).join('')}</div>${pdfLink(q)}</div>
  ${(q.segmentos?.length||q.segmentos_contexto?.length)?`<details class="details-box" ${q.modo_visual?'open':''}><summary>Ver a questão no PDF original</summary>${sourceImages(q)}</details>`:''}
  ${q.contexto?`<details class="details-box" open><summary>Texto associado</summary><div class="context prewrap">${h(q.contexto)}</div></details>`:''}
  <div class="question-text prewrap">${h(q.enunciado)}</div>
  <form id="answer-form"><div class="alternatives">${Object.entries(q.alternativas).map(([key,text])=>`<label class="alternative ${choice===key?'selected':''} ${reveal?.status_gabarito==='oficial'&&reveal?.gabarito===key?'correct':''} ${result?.correta===0&&choice===key?'wrong':''}"><input type="radio" name="escolha" value="${key}" ${choice===key?'checked':''} ${result||completed?'disabled':''}><span class="letter">${key}</span><span class="prewrap">${h(text)}</span></label>`).join('')}</div>
  ${!result&&!completed?`<div class="answer-actions"><button type="submit" class="primary">${session?'Salvar e avançar':'Responder'}</button><label class="check"><input type="checkbox" name="chute" ${answer?.chute?'checked':''}>Chutei / fiquei em dúvida</label></div>`:''}</form>
  ${result?`<div class="notice ${result.correta===1?'success':result.correta===0?'error':''}"><strong>${result.correta===1?'Resposta correta.':result.correta===0?'Resposta incorreta.':'Tentativa registrada sem correção oficial.'}</strong>${result.gabarito?` Gabarito oficial cadastrado: <strong>${result.gabarito}</strong>.`:''}${result.chute?' Você marcou como chute/dúvida.':''}${result.proxima?` Próxima revisão: ${h(result.proxima.split('-').reverse().join('/'))}.`:''}</div>`:''}
  ${completed&&!result?'<div class="notice">Questão não respondida. Não entrou no cálculo de aproveitamento.</div>':''}
  ${reveal?.fonte_gabarito?`<p class="subtle prewrap">Fonte cadastrada: ${h(reveal.fonte_gabarito)}</p>`:''}
  ${reveal?.status_gabarito==='informado'?`<div class="notice">Gabarito informado, sem confirmação oficial: ${h(reveal.gabarito)}. Não é usado para calcular acertos.</div>`:''}
  ${reveal?.explicacao?`<details class="details-box" open><summary>Comentário cadastrado</summary><div class="prewrap">${h(reveal.explicacao)}</div></details>`:''}
  ${!session?`<div class="answer-note"><label>Minhas anotações<textarea id="my-note" rows="3" placeholder="Registre seu raciocínio e o que revisar.">${h(q.anotacao||'')}</textarea></label><div class="actions spacer-top">${button('Salvar anotação','save-note')}${button(q.favorito?'★ Favorita':'☆ Favoritar','favorite',`data-id="${q.id}" data-value="${q.favorito?0:1}"`)}${button('Conferir / editar','edit',`data-id="${q.id}"`,'ghost')}${result?button('Próxima questão →','next-study','','primary'):''}</div></div>`:''}
  </section><aside class="study-sidebar"><section class="panel">${session?sessionSide(session):`<div class="eyebrow">ESTUDO LIVRE</div><h3>Uma questão por vez</h3><p class="muted small-text">A correção aparece após responder. O original está disponível para conferir a formatação e o texto.</p><div class="divide"><strong>${h(q.disciplina)}</strong></div><p class="subtle spacer-top">Erros e chutes voltam à revisão no dia seguinte. Acertos seguem o intervalo configurado.</p>`}</section></aside></div>`;
}
function sessionSide(s){
  if(s.estado==='concluida'){
    const graded=s.resultados.filter(r=>r.correta!==null),correct=graded.filter(r=>r.correta===1).length;
    return `<div class="eyebrow">SIMULADO CONCLUÍDO</div><h2>${graded.length?Math.round(correct/graded.length*100)+'%':'—'} de aproveitamento</h2><p class="muted small-text">${correct} acertos em ${graded.length} respostas com gabarito oficial.</p><p class="subtle">${s.resultados.length} respondidas · ${s.questoes.length-s.resultados.length} em branco · ${s.resultados.length-graded.length} sem correção.</p>${numberGrid(s)}`;
  }
  return `<div class="eyebrow">SIMULADO EM ANDAMENTO</div><span class="subtle">Tempo desde o início</span><div class="timer" id="session-timer">00:00</div><p class="muted small-text">${Object.keys(s.respostas).length} de ${s.questoes.length} respostas salvas</p>${numberGrid(s)}<div class="spacer-top">${button('Finalizar simulado','finish-session','','primary')}</div><p class="subtle spacer-top">Você pode sair e retomar. O gabarito fica oculto até finalizar.</p>`;
}
function numberGrid(s){return '<div class="number-grid">'+s.questoes.map((q,i)=>button(String(i+1),'session-number',`data-index="${i}" aria-label="Ir à questão ${i+1}"`,(s.respostas[q.id]?'answered ':'')+(i===state.index?'current':''))).join('')+'</div>';}
async function submitAnswer(){
  const f=Object.fromEntries(new FormData($('#answer-form')));
  if(!f.escolha)throw new Error('Selecione uma alternativa.');
  if(state.session){await saveSessionChoice();if(state.index<state.session.questoes.length-1)state.index++;renderStudy();state.started=Date.now();return;}
  const data=await api('responder',{id:state.question.id,escolha:f.escolha,chute:!!f.chute,segundos:Math.round((Date.now()-state.started)/1000),tentativa_id:state.attempt});renderStudy(data);
}
async function saveSessionChoice(){
  if(!state.session||state.session.estado!=='aberta'||!$('#answer-form'))return;
  const f=Object.fromEntries(new FormData($('#answer-form')));
  if(!f.escolha)return;
  const q=state.session.questoes[state.index],prev=state.session.respostas[q.id];
  const b={id:state.session.id,questao_id:q.id,escolha:f.escolha,chute:!!f.chute,segundos:(prev?.segundos||0)+Math.round((Date.now()-state.started)/1000)};
  await api('responder-sessao',b);state.session.respostas[q.id]=b;state.started=Date.now();
}

async function books(){
  await refresh();const bs=state.info.cadernos;
  $('#content').innerHTML=heading('Meus cadernos','Agrupe questões para revisar um assunto, uma prova ou seus pontos de atenção.',button('Novo caderno','book-new','','primary'))+
  (bs.length?`<div class="book-grid">${bs.map(b=>`<article class="book-card"><div class="book-icon">▤</div><h2>${h(b.nome)}</h2><p class="muted">${fmt(b.total)} questões</p><div class="actions">${button('Abrir caderno','book-open',`data-id="${b.id}"`,'primary')}${button('Excluir','book-delete',`data-id="${b.id}" data-name="${h(b.nome)}"`,'ghost small danger')}</div></article>`).join('')}</div>`:`<div class="panel">${empty('Seu primeiro caderno','Crie um caderno e adicione questões pela seleção do banco.',button('Criar caderno','book-new','','primary'))}</div>`);
}
function bookNew(){showModal('Criar caderno','<form id="book-form" class="modal-narrow"><label>Nome do caderno<input name="nome" required maxlength="120" placeholder="Ex.: Semântica — revisão"></label></form>',`${button('Cancelar','close-modal')}<button type="submit" form="book-form" class="primary">Criar caderno</button>`);}
function bookAdd(){if(!state.info.cadernos.length){toast('Crie um caderno primeiro. Sua seleção continuará disponível.');bookNew();return;}showModal('Adicionar '+fmt(selectionCount())+' questões',`<form id="book-add-form" class="modal-narrow"><label>Caderno<select name="id" required>${opt(state.info.cadernos.map(b=>({value:b.id,label:b.nome})),'','Selecione')}</select></label><p class="muted spacer-top">A mesma questão pode fazer parte de vários cadernos.</p></form>`,`${button('Cancelar','close-modal')}<button form="book-add-form" type="submit" class="primary">Adicionar</button>`);}

async function sessions(){
  const ss=await api('sessoes');
  $('#content').innerHTML=heading('Simulados','Resolva sem ver o gabarito e confira o resultado ao finalizar.',button('Criar simulado','new-session','','primary'))+
  (ss.length?`<div class="panel table-wrap"><table><thead><tr><th>Simulado</th><th>Questões</th><th>Início</th><th>Situação</th><th></th></tr></thead><tbody>${ss.map(s=>`<tr><td><strong>${h(s.nome)}</strong></td><td>${s.total}</td><td>${datefmt(s.criado)}</td><td><span class="pill ${s.estado==='concluida'?'green':'amber'}">${s.estado==='concluida'?'Concluído':'Em andamento'}</span></td><td>${button(s.estado==='concluida'?'Ver resultado':'Continuar','session-open',`data-id="${s.id}"`,'small')}</td></tr>`).join('')}</tbody></table></div>`:`<div class="panel">${empty('Prepare um simulado','Os simulados usam questões completas e com assuntos revisados. Você pode incluir questões sem gabarito, que ficarão sem correção oficial.',button('Escolher questões','nav-questoes','','primary'))}</div>`);
}
function newSession(){
  const useFilters=state.view==='questoes';state.sessionFilter=useFilters?{...state.filter}:{prontas:true};
  showModal('Criar simulado',`<form id="session-form" class="form-stack modal-narrow"><div class="notice">${useFilters?'Serão utilizados os filtros atuais do banco, somente com questões prontas.':'Serão usadas questões prontas de todo o acervo. Para escolher assuntos, crie o simulado pela tela Questões após filtrar.'}</div><label>Nome<input name="nome" required value="Simulado ${new Date().toLocaleDateString('pt-BR')}"></label><label>Quantidade máxima<input name="quantidade" type="number" min="1" max="300" value="20" required></label><label class="check"><input name="embaralhar" type="checkbox" checked>Embaralhar a ordem das questões</label><label class="check"><input name="oficial" type="checkbox">Usar somente questões com gabarito oficial</label><p class="subtle">Se houver menos questões disponíveis, o simulado terá a quantidade encontrada. O conteúdo e o gabarito são preservados como estavam na criação.</p></form>`,`${button('Cancelar','close-modal')}<button form="session-form" type="submit" class="primary">Começar simulado</button>`);
}
async function openSession(id){state.session=await api('sessao?id='+id);state.index=0;state.started=Date.now();renderStudy();}

async function history(){
  const [rs,p]=await Promise.all([api('historico'),api('painel')]);
  $('#content').innerHTML=heading('Seu histórico','Últimas 200 tentativas. Cada resposta mantém o gabarito usado naquele momento.')+
  `<div class="two-col spacer-bottom"><section class="panel"><h2>Atividade recente</h2>${p.dias.length?p.dias.slice().reverse().map(d=>`<div class="chart-row"><span>${d.dia.split('-').reverse().join('/')}</span><progress value="${d.total}" max="${Math.max(...p.dias.map(x=>x.total))}"></progress><span>${d.total} resp.</span></div>`).join(''):empty('Ainda sem respostas','Seu ritmo de estudo aparecerá aqui.')}</section><section class="panel"><h2>Revisão programada</h2><p class="muted">Erros e chutes ficam disponíveis no dia seguinte. Acertos ficam para ${p.intervalo} dias depois.</p><p class="subtle">O intervalo não esconde questões no banco: ative “Respeitar intervalo de revisão” quando quiser aplicá-lo ao filtro.</p>${button('Abrir revisão de hoje','due-list','','primary')}</section></div>
  <div class="panel table-wrap"><table><thead><tr><th>Quando</th><th>Prova / questão</th><th>Resposta</th><th>Resultado</th><th>Revisão</th><th></th></tr></thead><tbody>${rs.map(r=>`<tr><td>${datefmt(r.criado)}</td><td class="filename">${h(r.prova)}<br><strong>Q${r.numero}</strong>${r.sessao_id?' · Simulado':''}</td><td>${h(r.escolha)}${r.chute?' · Chute':''}</td><td>${resultLabel(r)}</td><td>${r.proxima?r.proxima.split('-').reverse().join('/'):'—'}</td><td>${button('Abrir','study',`data-id="${r.questao_id}"`,'small')}</td></tr>`).join('')||'<tr><td colspan="6">Nenhuma tentativa registrada.</td></tr>'}</tbody></table></div>`;
}

async function imports(){
  await refresh();
  $('#content').innerHTML=heading('Provas e importação','Traga os PDFs para seu acervo. As questões extraídas começam pendentes de conferência.',button('Classificar assuntos','nav-ia')+button('Conferir importadas','review-list'))+
  `<div class="two-col spacer-bottom"><section class="upload"><h3>Adicionar provas em PDF</h3><p class="muted small-text">Selecione uma ou várias provas do seu computador.</p><input id="pdf-files" type="file" accept=".pdf,application/pdf" multiple aria-label="Arquivos PDF"><div class="actions">${button('Importar selecionados','upload','','primary')}${button('Ler pasta provas_entrada','import-folder')}</div><div id="upload-status" class="status-inline spacer-top"></div></section><section class="panel"><h2>Como a importação funciona</h2><ol class="help-list"><li>Extração por perfis de FGV, IBFC e Cesgranrio.</li><li>Conferência do conteúdo com o PDF original.</li><li>Classificação dos assuntos e cadastro de gabarito, quando disponível.</li><li>Liberação para resolver e montar simulados.</li></ol><p class="subtle">PDF digitalizado e layouts diferentes podem exigir cadastro manual. O original fica acessível mesmo quando não há extração automática.</p></section></div><div id="job"></div>
  <section class="panel"><div class="row spacer-bottom"><h2>Provas do acervo</h2><span class="pill">${state.info.provas.length} provas</span></div>${state.info.provas.length?`<div class="table-wrap"><table><thead><tr><th>Prova</th><th>Banca / ano</th><th>Questões</th><th>Situação</th><th>Ações</th></tr></thead><tbody>${state.info.provas.map(p=>`<tr><td class="filename"><strong>${h(p.nome)}</strong><br><span class="subtle">${h(p.orgao)}${p.caderno?' · '+h(p.caderno):''}</span></td><td>${h(p.banca||'Não cadastrada')}<br>${h(p.ano)}</td><td>${p.total} extraídas<br><span class="subtle">${p.prontas} prontas</span></td><td>${p.erro?`<details><summary class="pill amber">Revisar extração</summary><p class="small-text prewrap">${h(p.erro)}</p></details>`:'<span class="pill green">Importada</span>'}</td><td><div class="actions">${button('Questões','exam-questions',`data-id="${p.id}"`,'small')}${button('Dados','exam-edit',`data-id="${p.id}"`,'small')}${button('Gabarito','exam-key',`data-id="${p.id}"`,'small')}<a href="/pdf/${p.id}.pdf" target="_blank" rel="noopener" class="btn-link">PDF ↗</a></div></td></tr>`).join('')}</tbody></table></div>`:empty('Nenhuma prova adicionada','Comece pelos seus PDFs. Você também pode usar as amostras enviadas anteriormente, disponíveis na pasta provas_entrada.')}</section>`;
  pollJob();
}
async function pollJob(){
  clearTimeout(jobTimer);if(state.view!=='importar'||!$('#job'))return;
  try{const j=await api('importacao');$('#job').innerHTML=j.total?`<div class="panel spacer-bottom"><div class="row"><h3>${j.ativo?'Importando…':j.parar?'Importação interrompida após o arquivo atual':'Importação concluída'}</h3>${j.ativo?button('Parar após este arquivo','stop-import','','small'):button('Atualizar lista','refresh-imports','','small')}</div><p class="muted small-text">${j.feitos} de ${j.total} arquivos · ${j.novas} novas questões</p><div class="progress-track"><progress max="${j.total}" value="${j.feitos}"></progress></div><p class="small-text prewrap">${h(j.atual)}</p><details><summary>Resultados por arquivo</summary>${j.resultados.map(r=>`<div class="divide small-text"><strong>${h(r.arquivo)}</strong> — ${r.novas} novas${r.erro?`<div class="notice error">${h(r.erro)}</div>`:r.nota?`<p class="muted">${h(r.nota)}</p>`:''}</div>`).join('')}</details></div>`:'';if(j.ativo)jobTimer=setTimeout(pollJob,1200);}catch(e){renderError(e);}
}
async function upload(){
  const files=[...$('#pdf-files').files];if(!files.length)throw new Error('Selecione os PDFs primeiro.');
  const names=[];for(let i=0;i<files.length;i++){const f=files[i];$('#upload-status').textContent=`Enviando ${i+1}/${files.length}: ${f.name}`;const res=await fetch('/api/enviar-pdf?nome='+encodeURIComponent(f.name),{method:'POST',headers:{'X-Local-Token':state.info.token,'Content-Type':'application/pdf'},body:f});const data=await res.json();if(!res.ok)throw new Error(data.erro);names.push(data.nome);}
  await api('importar',{nomes:names});$('#upload-status').textContent='Arquivos recebidos. Acompanhe a extração abaixo.';pollJob();
}
function examEdit(id){const p=state.info.provas.find(p=>p.id===id);state.exam=id;showModal('Dados da prova',`<form id="exam-form" class="form-stack modal-narrow">${[['nome','Nome da prova'],['banca','Banca'],['ano','Ano'],['orgao','Órgão / instituição'],['cargo','Cargo'],['caderno','Tipo / caderno / cor da prova']].map(([k,l])=>`<label>${l}<input name="${k}" value="${h(p[k])}" ${k==='nome'?'required':''}></label>`).join('')}</form>`,`${button('Cancelar','close-modal')}<button form="exam-form" type="submit" class="primary">Salvar dados</button>`);}
function examKey(id){
  const p=state.info.provas.find(p=>p.id===id);state.exam=id;state.keyPreview=null;
  showModal('Cadastrar gabarito · '+h(p.nome),`<form id="key-form" class="form-stack modal-narrow"><div class="notice">Confira banca, cargo, ano e tipo de caderno. O aplicativo não deduz respostas nem interpreta automaticamente o PDF de gabarito.</div><p class="small-text">Caderno cadastrado: <strong>${h(p.caderno||'Não informado')}</strong></p><label>Número e resposta — uma questão por linha<textarea name="texto" rows="10" placeholder="1;A&#10;2;C&#10;3;X"></textarea></label><p class="subtle">Use X para anulada. Aceita também “1 A”. Revise cada linha antes de salvar.</p><label>Fonte oficial<input name="fonte" placeholder="Nome do documento ou endereço; versão definitiva/preliminar"></label><div id="key-preview"></div><label class="check"><input name="confirmado" type="checkbox">Conferi as respostas e o vínculo com esta prova e este caderno.</label></form>`,`${button('Gerar prévia','key-preview')}<button id="key-save" form="key-form" type="submit" class="primary" disabled>Salvar gabarito conferido</button>`);
}

async function settings(){
  const p=await api('painel');$('#content').innerHTML=heading('Dados e backup','O histórico fica salvo na hospedagem, independente do navegador.')+
  `<div class="two-col"><section class="panel"><h2>Proteja seu progresso</h2><p class="muted">O backup reúne o banco, suas respostas, classificações, cadernos, simulados e os PDFs originais.</p><div class="actions">${button('Criar e baixar backup','backup','','primary')}</div><div id="backup-result"></div><div class="notice">Para levar um backup local à hospedagem, siga a seção Restaurar seu acervo no arquivo <strong>GUIA_RAILWAY.md</strong>. A restauração preserva os dados anteriores no volume.</div><p class="subtle">Baixe também uma cópia do backup para seu computador. Fechar o navegador não apaga o progresso.</p></section><section class="panel"><h2>Intervalo de revisão</h2><form id="settings-form" class="form-stack"><label>Revisar acertos depois de<select name="intervalo">${[7,8,9,10].map(n=>`<option value="${n}" ${p.intervalo===n?'selected':''}>${n} dias</option>`).join('')}</select></label><p class="muted small-text">Erros e chutes: dia seguinte. Tentativas sem gabarito oficial não recebem acerto/erro. A mudança vale para as próximas respostas.</p><button type="submit" class="primary">Salvar preferência</button></form></section></div>
  <section class="panel spacer-top"><h2>Sobre esta versão</h2><p>Banco de Questões Local ${h(state.info.versao)}. Acesso privado na hospedagem. Claude por API exige chave e pode cobrar pelo uso.</p><p class="muted small-text">A extração automática cobre perfis específicos de FGV, IBFC e Cesgranrio; não há OCR nesta versão. Questões de outros layouts podem ser cadastradas manualmente vinculadas ao PDF. A classificação pode ser feita pela IA local, pela API configurada ou por você, e permanece revisável. Importar uma prova não confirma sua origem oficial ou a qualidade da extração.</p><p class="muted small-text">Os resultados do histórico preservam a correção feita na data da tentativa. Cadastrar um gabarito depois não altera tentativas anteriores. Refaça a questão para registrar uma nova correção.</p></section>`;
}

async function classification(){
  await refresh();const s=await api('ia'),j=s.job;
  const modo=j.modo==='api'?'api':s.instalacao.disponivel?'hibrido':'regras';
  state.iaAPI=s.api;state.iaActive=j.ativo;state.iaInstalled=s.instalacao.disponivel;
  $('#content').innerHTML=heading('Classificação','Escolha a IA local ou Claude por API para organizar os assuntos.',button('Configurar Claude / API','api-setup')+button('Baixar diagnóstico','ia-report')+button('Ver questões','review-list'))+
  `<div class="two-col spacer-bottom"><section class="panel"><div class="row"><h2>Classificação no servidor</h2><span class="pill ${s.instalacao.disponivel?'green':'amber'}">${s.instalacao.disponivel?'IA instalada':'Instalação inicial'}</span></div><p class="muted">${h(s.instalacao.mensagem)}</p>${s.instalacao.disponivel?'':`<div class="notice"><strong>Como ativar a IA local</strong><p>No Railway, use <strong>Claude por API</strong> ou <strong>Somente regras</strong>. O modelo local não vem instalado nesta hospedagem.</p><p>Para usar Claude por API, basta configurar a chave e o modelo; esta instalação é opcional.</p></div>`}<p class="small-text">Neste modo, as regras são aplicadas no servidor. Seus dados ficam no volume da hospedagem. O modelo é descarregado ao concluir ou pausar o lote.</p><p class="subtle">Classificações que você revisou são preservadas. A IA identifica assuntos; não responde questões nem cria gabaritos.</p></section>
  <section class="panel"><h2>Iniciar um lote</h2><form id="ia-form" class="form-stack"><label>Tipo de análise<select name="modo"><option value="hibrido" ${!s.instalacao.disponivel?'disabled':''} ${modo==='hibrido'?'selected':''}>Regras + IA local</option><option value="regras" ${modo==='regras'?'selected':''}>Somente regras · sem instalação da IA</option><option value="api" ${modo==='api'?'selected':''}>Claude por API</option></select></label><label>Provas<select name="prova_id">${opt(state.info.provas.map(p=>({value:p.id,label:p.nome})),j.prova_id,'Todo o acervo')}</select></label><div class="form-grid"><label>Questões por lote<select name="limite">${[25,100,500,0].map(n=>`<option value="${n}" ${Number(j.limite??25)===n?'selected':''}>${n?n+' questões':'Todas as pendentes'}</option>`).join('')}</select></label><label>Uso do processador<select name="threads">${[1,2,4,8,16].map(n=>`<option value="${n}" ${Number(j.threads||2)===n?'selected':''}>${n} thread${n>1?'s':''}${n===1?' · econômico':n===2?' · recomendado':' · mais processamento'}</option>`).join('')}</select></label></div><div id="api-lote" class="hidden"><label class="check"><input name="somente_pendentes" type="checkbox" ${j.somente_pendentes!==false?'checked':''}>Enviar apenas questões com classificação pendente</label><p id="api-resumo" class="subtle"></p><div class="notice">Ao iniciar, o texto, as alternativas e o contexto destas questões serão enviados ao fornecedor configurado. A API pode cobrar pelo uso. Uma requisição por questão, sem tentativas pagas automáticas; comece com 25. Desmarcar a opção acima permite reclassificar resultados automáticos, preservando revisões humanas.</div></div><label class="check"><input name="reanalisar" type="checkbox">Analisar novamente sugestões pendentes já processadas</label><p class="subtle">Continuar pula análises concluídas. Os resultados são salvos por questão. Threads se aplicam somente ao modelo local; Claude roda no fornecedor.</p><button id="ia-start" type="submit" class="primary" ${j.ativo?'disabled':''}>Classificar / continuar</button></form></section></div>
  <div class="notice">A IA local usa pistas e comparação semântica. Claude recebe o conteúdo textual e o catálogo de assuntos; respostas fora do catálogo, incertas ou inválidas ficam para conferência. A conferência do PDF continua separada.</div><div id="ia-summary"></div><div id="ia-progress"></div>`;
  syncIAMode();await pollIA();
}
function syncIAMode(){
  const f=$('#ia-form');if(!f)return;const modo=f.elements.modo.value;
  $('#api-lote').classList.toggle('hidden',modo!=='api');f.elements.threads.disabled=modo!=='hibrido';
  $('#ia-start').disabled=state.iaActive||(modo==='hibrido'&&!state.iaInstalled)||(modo==='api'&&!state.iaAPI?.pronta);
  $('#api-resumo').textContent=state.iaAPI?.pronta?'Modelo: '+state.iaAPI.modelo+' · '+state.iaAPI.base_url:'Configure a chave, o endereço e o modelo pelo botão Configurar Claude / API.';
}
async function apiSetup(){
  const s=await api('ia'),c=s.api;state.iaAPI=c;
  showModal('Claude / API',`<form id="api-config-form" class="form-stack modal-narrow"><label>Formato da API<select name="protocolo">${opt([{value:'anthropic',label:'Anthropic · API oficial ou compatível'},{value:'openai',label:'Compatível com OpenAI · outro fornecedor'}],c.protocolo,'Escolha o formato')}</select></label><label>URL base<input name="base_url" type="url" required value="${h(c.base_url)}" placeholder="https://api.anthropic.com"></label><p class="subtle">Se sua chave for de outro fornecedor, use o endereço e o formato informados por ele. Pode terminar em /v1; não acrescente /messages ou /chat/completions.</p><label>Chave da API<input name="chave" type="password" autocomplete="off" spellcheck="false" placeholder="${c.chave_configurada?'Chave já configurada · deixe vazio para manter':'Cole a chave somente aqui'}"></label><label class="check"><input name="guardar_chave" type="checkbox" ${c.chave_guardada?'checked':''} ${c.pode_guardar?'':'disabled'}>Guardar a chave protegida pelo meu usuário do Windows</label><p class="subtle">Nesta hospedagem, a chave digitada vale até reiniciar o serviço. Para mantê-la entre reinicializações, configure BANCO_API_KEY em Variables do Railway. Não é gravada no navegador nem incluída no backup.</p><label class="check"><input name="apagar_chave" type="checkbox">Remover a chave cadastrada</label><label>ID exato do modelo<input name="modelo" list="modelos-api" value="${h(c.modelo)}" placeholder="Informe o ID fornecido pelo seu serviço"></label><datalist id="modelos-api"></datalist><div class="form-grid"><label>Tempo máximo por questão (s)<input name="timeout" type="number" min="15" max="180" value="${c.timeout}" required></label><label>Máximo de tokens da resposta<input name="max_tokens" type="number" min="400" max="2000" value="${c.max_tokens}" required></label></div><p class="subtle">Testar conexão consulta a lista de modelos, sem enviar questões. Alguns fornecedores exigem informar o modelo manualmente.</p><div id="api-config-result" aria-live="polite"></div></form>`,`${button('Fechar','close-modal')}${button('Salvar e testar conexão','api-test')}<button form="api-config-form" type="submit" class="primary">Salvar configuração</button>`);
}
async function saveAPI(testar=false){
  const form=$('#api-config-form'),f=Object.fromEntries(new FormData(form));
  const c=await api('ia/configurar-api',{...f,guardar_chave:!!f.guardar_chave,apagar_chave:!!f.apagar_chave});
  form.elements.chave.value='';form.elements.apagar_chave.checked=false;state.iaAPI=c;
  if(testar){
    const r=await api('ia/testar-api',{});
    $('#modelos-api').innerHTML=r.modelos.map(m=>`<option value="${h(m.id)}">${h(m.nome)}</option>`).join('');
    $('#api-config-result').innerHTML=`<div class="notice success">${h(r.mensagem)}${r.modelos.length?'<p>Modelos carregados: '+r.modelos.length+'. Digite ou escolha um no campo acima e salve.</p>':''}</div>`;
  }else{$('#modal').close();toast('Configuração da API salva.');await classification();$('#ia-form [name=modo]').value='api';syncIAMode();}
}
async function pollIA(){
  clearTimeout(iaTimer);if(state.view!=='ia'||!$('#ia-progress'))return;
  try{
    const s=await api('ia'),j=s.job,a=s.acervo;
    if(state.view!=='ia'||!$('#ia-progress'))return;
    state.iaActive=j.ativo;state.iaInstalled=s.instalacao.disponivel;state.iaAPI=s.api;syncIAMode();
    $('#ia-summary').innerHTML=`<div class="stats-grid spacer-top">${[['Classificadas automaticamente',a.automaticas,'ia-list-auto'],['Sugestões para conferir',a.revisar,'ia-list-review'],['Texto insuficiente',a.incompletas,'ia-list-incomplete'],['Fora do catálogo',a.fora_catalogo||0,'ia-list-outside'],['Avisos de conteúdo',a.alertas_conteudo||0,'ia-list-content'],['Revisadas por você',a.revisadas,'ia-list-manual']].map(([l,n,act])=>`<div class="stat"><div class="label">${l}</div><span class="value">${fmt(n)}</span>${button('Ver questões',act,'','small ghost')}</div>`).join('')}</div>`;
    $('#ia-progress').innerHTML=j.total?`<section class="panel spacer-top"><div class="row"><h2>${j.ativo?'Classificando…':j.erro?'Lote interrompido':j.pausada?'Lote pausado':'Lote concluído'}</h2>${j.ativo?button('Pausar após esta questão','ia-pause','','small'):''}</div><p class="muted">${j.feitos} de ${j.total} analisadas · ${j.automaticas} classificadas · ${j.revisar} sugestões · ${j.incompletas} sem texto suficiente · ${j.fora_catalogo||0} fora do catálogo · ${j.preservadas} preservadas</p><p class="subtle">Aplicações por regras: ${j.regras||0} · por comparação semântica: ${j.semanticas||0} · por API: ${j.api||0}${j.falhas?' · falhas individuais: '+j.falhas:''}</p><div class="progress-track"><progress max="${j.total}" value="${j.feitos}"></progress></div><p class="subtle prewrap">${h(j.atual)}${j.segundos?' · '+Math.round(j.segundos)+' s neste ambiente':''}</p>${j.erro?`<div class="notice error">${h(j.erro)}</div>`:''}<details><summary>Resultados recentes do lote</summary><div class="table-wrap"><table><thead><tr><th>Questão</th><th>Resultado</th><th>Assunto</th><th></th></tr></thead><tbody>${(j.resultados||[]).slice().reverse().map(r=>`<tr><td class="filename">Q${r.numero}<br><span class="subtle">${h(r.prova)}</span></td><td>${h(({automatica:'Classificada',revisar:'Conferir sugestão',incompleta:'Texto insuficiente',fora_catalogo:'Fora do catálogo',preservada:'Edição preservada'})[r.estado])}</td><td>${h(r.assuntos.join('; ')||r.motivo)}</td><td>${button('Conferir','edit',`data-id="${h(r.id)}"`,'small')}</td></tr>`).join('')}</tbody></table></div></details></section>`:'';
    if(j.modo==='api'&&!j.total&&!j.ativo&&(j.atual||j.erro))$('#ia-progress').innerHTML=`<div class="notice ${j.erro?'error':''}">${h(j.erro||j.atual)}</div>`;
    if(j.modo==='api'&&j.ativo&&j.preparando)$('#ia-progress').innerHTML='<div class="notice">Preparando a fila da API… '+button('Pausar','ia-pause','','small')+'</div>';
    if(j.modo==='api'&&j.total){const p=document.createElement('p');p.className='subtle';p.textContent=`API: ${j.requisicoes||0} requisições · ${fmt(j.tokens_entrada)} tokens de entrada · ${fmt(j.tokens_saida)} de saída · ${fmt(j.tokens_cache)} de cache. O preço depende do fornecedor e do modelo.`;$('#ia-progress').prepend(p);}
    if(j.ativo)iaTimer=setTimeout(pollIA,3000);
  }catch(e){renderError(e);}
}
function iaList(f){state.filter={prontas:false,pagina:1,...f};clearSelection();return nav('questoes');}

const actions={
  logout:async()=>{await api('logout',{});window.location.assign('/login');},
  'api-setup':apiSetup,
  'api-test':async()=>{try{await saveAPI(true);}catch(e){$('#api-config-result').textContent=e.message;throw e;}},
  reload:()=>nav(state.view),
  'nav-ia':()=>nav('ia'),
  'ia-pause':async()=>{await api('ia/pausar',{});toast('A análise vai pausar ao concluir esta questão.');},
  'ia-list-auto':()=>iaList({classificacao:'automatica'}),
  'ia-list-review':()=>iaList({ia:'revisar'}),
  'ia-list-incomplete':()=>iaList({ia:'incompleta'}),
  'ia-list-outside':()=>iaList({ia:'fora_catalogo'}),
  'ia-list-content':()=>iaList({ia:'alertas_conteudo'}),
  'ia-report':()=>{const a=document.createElement('a');a.href='/api/ia/relatorio?prova_id='+encodeURIComponent($('#ia-form [name=prova_id]')?.value||'');a.download='diagnostico_classificacao.csv';a.click();},
  'ia-list-manual':()=>iaList({classificacao:'revisada'}),
  'ia-use':b=>{const f=$('#edit-form');f.elements.disciplina.value=b.dataset.discipline;f.elements.assuntos.value=b.dataset.topic;f.elements.classificacao.value='revisada';toast('Assunto preenchido. Salve para confirmar sua revisão.');},
  'nav-importar':()=>nav('importar'),'nav-questoes':()=>nav('questoes'),'nav-simulados':()=>nav('simulados'),
  'review-list':()=>{state.filter={pagina:1,prontas:false};clearSelection();return nav('questoes');},
  'due-list':()=>{state.filter={pagina:1,prontas:true,situacao:'revisar'};clearSelection();return nav('questoes');},
  'clear-filters':()=>{state.filter={prontas:true,pagina:1};clearSelection();return questions();},
  'page-prev':()=>{state.filter.pagina--;return questions();},'page-next':()=>{state.filter.pagina++;return questions();},
  'select-all':()=>{state.all=true;state.selected.clear();$$('[data-select]').forEach(c=>c.checked=true);$('#select-page').checked=true;selectionBar();},
  deselect:()=>{clearSelection();$$('[data-select],#select-page').forEach(c=>c.checked=false);selectionBar();},
  'close-modal':()=>$('#modal').close(),edit:b=>edit(b.dataset.id),'new-question':()=>edit(),bulk,
  favorite:async b=>{await api('pessoal',{id:b.dataset.id,favorito:b.dataset.value==='1'});b.dataset.value=b.dataset.value==='1'?'0':'1';b.textContent=b.dataset.value==='0'?'★ Favorita':'☆ Favoritar';if(state.question?.id===b.dataset.id)state.question.favorito=b.dataset.value==='0';},
  study:b=>study(b.dataset.id),
  'save-note':async()=>{await api('pessoal',{id:state.question.id,anotacao:$('#my-note').value});state.question.anotacao=$('#my-note').value;toast('Anotação salva.');},
  'next-study':async()=>{let ids=state.list?.itens.filter(ready).map(q=>q.id)||[];let i=ids.indexOf(state.question.id);if(i>=0&&i<ids.length-1)return study(ids[i+1]);toast('Você chegou ao fim das questões desta página.');return nav('questoes');},
  'book-new':bookNew,'book-add':bookAdd,
  'book-open':b=>{state.filter={pagina:1,caderno_id:b.dataset.id,prontas:false};clearSelection();return nav('questoes');},
  'book-delete':async b=>{if(confirm(`Excluir o caderno “${b.dataset.name}”? As questões e o histórico serão preservados.`)){await api('caderno',{acao:'excluir',id:b.dataset.id});return books();}},
  'book-remove':async()=>{if(state.all)throw new Error('Para retirar do caderno, selecione as questões desta página.');await api('caderno',{acao:'remover',id:state.filter.caderno_id,ids:[...state.selected]});clearSelection();await questions();},
  export:()=>{if(!state.list?.total)throw new Error('Não há questões para exportar.');const a=document.createElement('a');a.href='/api/exportar?filtro='+encodeURIComponent(JSON.stringify(state.filter));a.download='questoes_exportadas.json';a.click();toast('O JSON inclui os gabaritos cadastrados; não substitui o backup completo.');},
  'new-session':newSession,'session-open':b=>openSession(b.dataset.id),
  'session-number':async b=>{await saveSessionChoice();state.index=Number(b.dataset.index);state.started=Date.now();renderStudy();},
  'finish-session':async()=>{await saveSessionChoice();const s=state.session;const blank=s.questoes.length-Object.keys(s.respostas).length;if(!confirm(`Finalizar o simulado? ${blank?blank+' questão(ões) está(ão) em branco.':'Todas as questões têm resposta salva.'}`))return;state.session=await api('finalizar-sessao',{id:s.id});renderStudy();},
  upload,'import-folder':async()=>{await api('importar',{});pollJob();},'stop-import':async()=>{await api('parar-importacao',{});toast('A importação vai parar ao terminar este arquivo.');},'refresh-imports':imports,
  'exam-questions':b=>{state.filter={pagina:1,prontas:false,prova_id:b.dataset.id};clearSelection();return nav('questoes');},'exam-edit':b=>examEdit(b.dataset.id),'exam-key':b=>examKey(b.dataset.id),
  'key-preview':async()=>{const f=Object.fromEntries(new FormData($('#key-form')));state.keyPreview=await api('gabarito-previa',{...f,prova_id:state.exam});$('#key-preview').innerHTML=`<div class="key-preview"><table><thead><tr><th>Questão</th><th>Atual</th><th>Novo</th></tr></thead><tbody>${state.keyPreview.itens.map(i=>`<tr><td>${i.numero}</td><td>${h(i.anterior||'Sem')}</td><td>${h(i.gabarito)}</td></tr>`).join('')}</tbody></table></div><p class="subtle">${state.keyPreview.itens.length} registros. A prévia precisa corresponder ao texto salvo.</p>`;$('#key-save').disabled=false;},
  backup:async()=>{toast('Preparando backup com os PDFs…');const r=await api('backup',{});const url='/api/baixar-backup?nome='+encodeURIComponent(r.nome);$('#backup-result').innerHTML=`<div class="notice success">Backup criado. <a href="${url}" download>Baixar ${h(r.nome)}</a></div>`;const a=document.createElement('a');a.href=url;a.download=r.nome;a.click();}
};

document.addEventListener('click',async e=>{
  const b=e.target.closest('button[data-action],button[data-view]');if(!b||b.disabled)return;e.preventDefault();
  const action=b.dataset.action;
  if(state.busy)return;
  state.busy=true;b.disabled=true;
  try{
    if(b.dataset.view){await saveSessionChoice();await nav(b.dataset.view);}
    else if(actions[action]){if(action?.startsWith('nav-'))await saveSessionChoice();await actions[action](b);}
  }catch(err){renderError(err);}finally{state.busy=false;if(b.isConnected)b.disabled=false;}
});
document.addEventListener('submit',async e=>{
  e.preventDefault();if(state.busy)return;state.busy=true;const submit=e.submitter;if(submit)submit.disabled=true;
  try{
    const f=Object.fromEntries(new FormData(e.target));
    if(e.target.getAttribute('id')==='filters'){state.filter=readFilter();clearSelection();await questions();}
    else if(e.target.getAttribute('id')==='ia-form'){await api('ia/iniciar',{prova_id:f.prova_id,modo:f.modo,threads:Number(f.threads||2),limite:Number(f.limite),reanalisar:!!f.reanalisar,somente_pendentes:!!f.somente_pendentes});await pollIA();}
    else if(e.target.getAttribute('id')==='api-config-form')await saveAPI();
    else if(e.target.getAttribute('id')==='edit-form')await saveEdit(submit?.name==='proxima');
    else if(e.target.getAttribute('id')==='bulk-form'){const r=await api('lote',{...selectedPayload(),disciplina:f.disciplina,assuntos:f.assuntos.split(';').map(s=>s.trim()).filter(Boolean),substituir:!!f.substituir,classificacao:f.classificacao,revisao:f.revisao,conferida:!!f.conferida});$('#modal').close();clearSelection();toast(`${r.alteradas} questões atualizadas.`);await questions();}
    else if(e.target.getAttribute('id')==='answer-form')await submitAnswer();
    else if(e.target.getAttribute('id')==='book-form'){await api('caderno',{nome:f.nome});$('#modal').close();await refresh();toast('Caderno criado.');if(state.view==='cadernos')await books();}
    else if(e.target.getAttribute('id')==='book-add-form'){await api('caderno',{...selectedPayload(),id:f.id,acao:'adicionar'});$('#modal').close();toast('Questões adicionadas ao caderno.');}
    else if(e.target.getAttribute('id')==='session-form'){if(f.oficial)state.sessionFilter.gabarito='oficial';state.session=await api('sessao',{filtro:state.sessionFilter,nome:f.nome,quantidade:Number(f.quantidade),embaralhar:!!f.embaralhar});state.index=0;state.started=Date.now();$('#modal').close();renderStudy();}
    else if(e.target.getAttribute('id')==='exam-form'){await api('prova',{id:state.exam,...f});$('#modal').close();await imports();toast('Dados da prova salvos.');}
    else if(e.target.getAttribute('id')==='key-form'){await api('gabarito-salvar',{prova_id:state.exam,texto:f.texto,fonte:f.fonte,confirmado:!!f.confirmado,itens:state.keyPreview?.itens});$('#modal').close();await imports();toast('Gabarito cadastrado. Será usado nas próximas tentativas.');}
    else if(e.target.getAttribute('id')==='settings-form'){await api('configurar',{intervalo:Number(f.intervalo)});toast('Preferência salva.');}
  }catch(err){renderError(err);if(e.target.getAttribute('id')==='edit-form')$('#edit-status').textContent=err.message;}finally{state.busy=false;if(submit?.isConnected)submit.disabled=false;if(e.target.id==='ia-form')syncIAMode();}
});
document.addEventListener('change',e=>{
  const el=e.target;
  if(el.matches('#ia-form [name=modo]')){if(el.value==='api')$('#ia-form [name=limite]').value='25';syncIAMode();}
  if(el.matches('[data-select]')){if(state.all){state.all=false;state.selected=new Set(state.list.itens.map(q=>q.id));}if(el.checked)state.selected.add(el.dataset.select);else state.selected.delete(el.dataset.select);selectionBar();}
  if(el.id==='select-page'){if(state.all){state.all=false;state.selected.clear();}state.list.itens.forEach(q=>el.checked?state.selected.add(q.id):state.selected.delete(q.id));$$('[data-select]').forEach(c=>c.checked=el.checked);selectionBar();}
  if((el.matches('#filters [name=revisao],#filters [name=classificacao]')&&['pendente','retida'].includes(el.value))||(el.matches('#filters [name=ia]')&&el.value))$('#filters [name=prontas]').checked=false;
  if(el.matches('#filters [name=disciplina]')){const temas=el.value?state.info.catalogo[el.value]||[]:[...new Set(Object.values(state.info.catalogo).flat())].sort();$('#filters [name=assunto]').innerHTML=opt(temas,'');}
  if(el.matches('#edit-form [name=disciplina]'))$('#edit-topic').innerHTML=opt(state.info.catalogo[el.value]||[],'','Escolha um assunto para adicionar');
  if(el.id==='edit-topic'&&el.value){const input=$('#edit-form [name=assuntos]');const a=input.value.split(';').map(x=>x.trim()).filter(Boolean);if(!a.includes(el.value))a.push(el.value);input.value=a.join('; ');el.value='';}
  if(el.matches('#answer-form [name=escolha]'))$$('.alternative').forEach(label=>label.classList.toggle('selected',label.querySelector('input').checked));
});
document.addEventListener('input',e=>{if(e.target.matches('#key-form [name=texto]')){state.keyPreview=null;$('#key-save').disabled=true;$('#key-preview').innerHTML='';}});
document.addEventListener('error',e=>{if(e.target instanceof HTMLImageElement&&e.target.classList.contains('image-source')){const p=document.createElement('p');p.className='notice error';p.textContent='Não foi possível exibir este recorte. Confira o PDF original e as páginas associadas no editor.';e.target.replaceWith(p);}},true);
setInterval(()=>{if($('#session-timer')&&state.session){const seconds=Math.max(0,Math.floor((Date.now()-new Date(state.session.criado).getTime())/1000));$('#session-timer').textContent=[Math.floor(seconds/3600),Math.floor(seconds%3600/60),seconds%60].map(n=>String(n).padStart(2,'0')).join(':');}},1000);
window.addEventListener('beforeunload',e=>{if($('#modal').open&&$('#edit-form')){e.preventDefault();e.returnValue='';}});
(async()=>{try{await refresh();await nav('painel');}catch(e){$('#content').innerHTML=empty('Não foi possível abrir o banco',h(e.message));}})();
