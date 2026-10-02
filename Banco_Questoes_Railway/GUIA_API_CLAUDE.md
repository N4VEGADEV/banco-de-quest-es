# Classificar assuntos com Claude por API

A versão Railway permite classificar questões pelo Claude sem instalar um modelo de IA local. O aplicativo, os PDFs e o banco SQLite ficam no serviço Railway; somente a classificação escolhida nesse modo usa o fornecedor da API. A opção de regras funciona sem API.

## Configuração

1. Entre no site com sua conta de administrador e abra **Classificação → Configurar Claude / API**.
2. Escolha o formato do seu serviço:

   | Serviço da chave | Formato | URL base |
   | --- | --- | --- |
   | Anthropic oficial | Anthropic | `https://api.anthropic.com` |
   | Outro fornecedor com protocolo Anthropic | Anthropic | Endereço informado pelo fornecedor |
   | Outro fornecedor com protocolo compatível com OpenAI | Compatível com OpenAI | Endereço informado pelo fornecedor; pode terminar em `/v1` |

3. Cole a chave **no campo do aplicativo**. Não acrescente a chave na URL. Use o endereço base da API fornecido pelo serviço.
4. Clique em **Salvar e testar conexão**. Isso consulta `/v1/models`, sem enviar questões ou solicitar geração. Os IDs retornados aparecerão como sugestões no campo do modelo. Se essa rota não existir, informe o ID manualmente conforme os dados do fornecedor.
5. Informe o **ID exato** do modelo Claude liberado para sua chave e salve. Nenhum modelo é escolhido automaticamente. Uma lista acessível não garante acesso a todos os modelos nela; a geração será verificada no primeiro lote.
6. Escolha **Claude por API**, selecione a prova e comece com **25 questões**.

O formato compatível com OpenAI é uma alternativa de protocolo para outros fornecedores. A chave e o modelo continuam sendo os do serviço que você configurou. O aplicativo não determina qual modelo esse serviço realmente utiliza.

O modo API usa somente a biblioteca padrão do Python, sem instalação adicional. Há uma requisição de classificação por questão, executada de cada vez. A quantidade de threads não acelera o Claude, que roda no fornecedor.

## Chave e dados enviados

Uma chave digitada no aplicativo fica somente na memória até reiniciar o serviço. Para mantê-la entre reinicializações, defina **BANCO_API_KEY** nas Variables do Railway. Não há armazenamento por usuário Windows nesta hospedagem.

O arquivo `/data/acervo/api_config.json` guarda endereço, protocolo, modelo, tempo máximo e limite de tokens, sem chave. A chave não volta nas respostas da interface, não é armazenada no navegador e não entra nos backups ou exportações. Ao trocar endereço ou protocolo com uma chave configurada, o programa exige a chave do novo fornecedor ou a remoção da anterior.

Para a API oficial, `ANTHROPIC_API_KEY` continua disponível como alternativa nas Variables do Railway. Essa variável só é usada com o endereço oficial da Anthropic. Remover a chave pelo formulário não apaga uma variável de ambiente definida fora do aplicativo; BANCO_API_KEY é reaplicada ao iniciar o serviço.

Cada classificação envia:

- Enunciado, alternativas e contexto textual da questão.
- Catálogo de disciplinas e assuntos cadastrados no aplicativo.
- Avisos sobre conteúdo incompleto ou visual.

Não envia o PDF, imagens, gabarito cadastrado, comentários de resolução, anotações, favoritos ou histórico de respostas. Dados que você incluiu dentro do próprio enunciado ou contexto serão parte do texto enviado. A classificação de uma questão visual usa somente seu texto; imagens continuam disponíveis localmente para conferência.

## Aplicação das categorias

O Claude recebe IDs de assuntos permitidos. O programa valida a resposta, aceita até três assuntos de uma mesma disciplina e procura no texto o trecho apresentado como evidência. A API oficial usa uma ferramenta com esquema JSON; o formato compatível pede JSON e passa pela mesma validação ao retornar.

Uma resposta com confiança qualitativa alta ou média e evidência reconhecida pode receber classificação automática. Confiança baixa, evidência ausente, resposta truncada ou formato inválido deixam a questão para conferência. A confiança informada pelo modelo **não é uma porcentagem de acerto**. Uma evidência presente não comprova que o assunto escolhido seja pedagogicamente correto.

Quando o assunto não existe no catálogo, a questão fica como **Fora do catálogo**. Crie a categoria no editor e inicie outro lote; a alteração do catálogo permite nova análise das pendentes. Nomes personalizados já cadastrados são incluídos no envio. Não há sincronização de taxonomia ou conteúdo com Qconcursos.

Questões com enunciado insuficiente ou conteúdo textual acima de 60.000 caracteres recebem aviso local, sem requisição de classificação. O programa não corta o texto silenciosamente nem inventa uma categoria para completar a contagem.

A classificação não libera conteúdo para resolver: o estado **Completa e conferida** ainda depende da conferência do PDF. Também não produz respostas, gabaritos ou justificativas de resolução.

## Lotes, custo e retomada

**Enviar apenas questões com classificação pendente** vem marcado. Assim você pode complementar a classificação feita na versão anterior, preservando as categorias automáticas existentes. Desmarcar permite incluir também classificações automáticas anteriores; classificações humanas revisadas e questões retidas continuam preservadas.

Resultados são salvos por questão. **Classificar / continuar** pula resultados já concluídos pela mesma integração, modelo, catálogo e conteúdo. Marque **Analisar novamente sugestões pendentes já processadas** para pedir nova avaliação das sugestões. Respostas com estrutura inválida podem ser reenviadas quando você iniciar outro lote.

**Pausar após esta questão** permite concluir e salvar a requisição em andamento. Depois disso, não inicia outra. Aguarde o lote encerrar antes de mudar a configuração. Se você editar uma questão durante a requisição, a edição é preservada e o resultado antigo não a sobrescreve.

Erros de chave, saldo, modelo, cota, conexão ou tempo máximo interrompem o lote. Os resultados anteriores ficam salvos. Não há repetição automática de requisições pagas. Confira o motivo e inicie novamente quando estiver resolvido. Em um tempo excedido, o fornecedor pode ter processado a requisição mesmo sem o aplicativo receber o resultado.

O painel mostra tentativas de requisição e tokens informados nas respostas recebidas, incluindo cache quando disponível. Consumo sem resposta não pode ser contado pelo aplicativo. Consulte o painel do fornecedor para custo e consumo definitivos; não há estimativa em dinheiro nem limite financeiro automático nesta versão. O tamanho do lote limita quantas questões serão processadas por execução.

## Atualizar sem perder o acervo

Siga a seção 7 de **GUIA_RAILWAY.md** para restaurar seu banco local. O backup preserva resultados de classificação, questões e histórico. A configuração da API e a chave ficam fora dele e precisam ser configuradas no novo serviço.

## Referências de protocolo e testes

- API de mensagens Anthropic: https://platform.claude.com/docs/en/api/messages/create
- Lista de modelos Anthropic: https://platform.claude.com/docs/en/api/models/list

O código está em `api_claude.py`, os lotes em `ia_servico.py` e os testes em `testes_api.py`. A entrega foi testada com fornecedor HTTP simulado; não foi usada chave real nem feita chamada paga. O carregamento de BANCO_API_KEY foi verificado nos testes do servidor privado.
