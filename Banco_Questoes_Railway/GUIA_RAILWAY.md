# Publicar seu banco privado no Railway

Esta versão tem uma conta de administrador, com acesso privado ao acervo inteiro. As credenciais são escolhidas por você no Railway. O site permite importar, classificar e resolver questões, manter histórico e baixar backups.

## 1. Enviar ao seu GitHub

1. Extraia o ZIP. Você verá a pasta **Banco_Questoes_Railway**.
2. Abra o repositório que deseja usar, de preferência privado.
3. Na aba **Code**, clique em **Add file → Upload files**.
4. Arraste a pasta **Banco_Questoes_Railway inteira** para a página. Assim ela entra como uma subpasta e preserva os arquivos que já estavam no repositório.
5. Confira os arquivos e clique em **Commit changes**.

Ao terminar, estes caminhos devem existir no GitHub:

- `Banco_Questoes_Railway/Dockerfile`
- `Banco_Questoes_Railway/online.py`
- `Banco_Questoes_Railway/wsgi.py`
- `Banco_Questoes_Railway/requirements-railway.txt`
- `Banco_Questoes_Railway/web/app.js`
- `Banco_Questoes_Railway/templates/login.html`

Envie o conteúdo extraído, não apenas o ZIP. Não envie sua pasta de dados local, backup, chave de API ou arquivo com senha ao GitHub. O pacote entregue contém código e duas provas de exemplo, sem seu banco pessoal.

Se você preferir colocar os arquivos diretamente na raiz de um repositório dedicado a esta versão, deixe o Root Directory do Railway vazio na etapa seguinte. O restante da configuração é igual.

## 2. Conectar o Railway ao repositório

1. Entre em https://railway.com e clique em **New Project**.
2. Escolha **Deploy from GitHub repo**.
3. Autorize o acesso ao seu repositório, se solicitado, e selecione-o.
4. Abra o serviço criado → **Settings → Source → Root Directory**.
5. Informe **`/Banco_Questoes_Railway`**, correspondente à pasta enviada na etapa 1.

O Railway detecta o `Dockerfile` nessa pasta. Ele instala o necessário e executa o servidor; você não precisa instalar Python ou IA no seu computador para usar o site online.

A primeira tentativa pode falhar antes de configurar as credenciais e o volume. Complete as próximas etapas e publique novamente. **Não use ABRIR.bat, iniciar.py ou servidor.py como Start Command.** Deixe o comando do Dockerfile, ou configure explicitamente:

```text
gunicorn --config gunicorn.conf.py wsgi:app
```

Este pacote usa configuração pelo painel e Dockerfile. Não exige `railway.toml`.

## 3. Criar o volume persistente

No projeto Railway, crie um **Volume** pelo menu de criação ou clicando com o botão direito no espaço do projeto. Conecte-o ao **serviço do banco** e configure:

| Campo | Valor |
| --- | --- |
| Mount Path | `/data` |

O programa grava o banco, PDFs, configurações sem chave e backups em `/data/acervo`. O volume precisa ter espaço para seu acervo e para backups. Arquivos fora dele não são preservados entre implantações.

Mantenha **uma réplica e uma região** para este serviço. Não adicione réplicas extras: a coordenação dos lotes foi preparada para um processo e o banco usa SQLite. O Gunicorn já oferece quatro threads para atender a interface.

## 4. Configurar sua conta

Abra o serviço → **Variables** e adicione os campos abaixo. Digite seus valores no painel; não os coloque em arquivos do GitHub.

| Nome | Valor que você informa |
| --- | --- |
| `ADMIN_USER` | Seu usuário, por exemplo `admin` |
| `ADMIN_PASSWORD` | Sua senha, de 12 a 200 caracteres |
| `SECRET_KEY` | Texto aleatório de pelo menos 32 caracteres |
| `DATA_DIR` | `/data/acervo` |
| `PORT` | `8080` |

O usuário aceita letras, números, ponto, `_`, `@` e `-`, de 3 a 80 caracteres. O programa recusa iniciar sem credenciais válidas. A senha é comparada por hash durante o login. A chave secreta assina a sessão; não precisa ser a senha nem a chave do Claude.

Para gerar a SECRET_KEY no seu computador, execute no PowerShell:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copie o resultado para a variável SECRET_KEY. Guarde-o; não é necessário mudar em cada publicação. Se não tiver Python no computador, use uma sequência aleatória gerada pelo seu gerenciador de senhas, com pelo menos 32 caracteres.

Cookies HTTPS estão ativados por padrão. **Não defina COOKIE_SECURE=0 no Railway**; essa opção existe apenas para testes locais por HTTP.

## 5. Publicar e abrir o site

1. Em **Settings → Deploy**, configure **Healthcheck Path: `/health`**. Mantenha uma réplica. Não coloque um comando de migração em Pre-deploy.
2. Aplique as alterações pendentes com **Deploy**. Confira os logs: o Gunicorn deve iniciar na porta **8080**.
3. Entre em **Settings → Networking → Public Networking → Generate Domain**.
4. Se solicitar a porta de destino, informe **8080**.
5. Abra o endereço HTTPS gerado. A primeira tela deve ser **Entrar · Banco de Questões**.
6. Entre com os valores de **ADMIN_USER** e **ADMIN_PASSWORD**.

O programa reconhece os domínios `*.up.railway.app` e o hostname do healthcheck Railway. Para um domínio próprio, acrescente `TRUSTED_HOSTS` nas Variables com o hostname, por exemplo `questoes.seudominio.com`, e configure o domínio no Railway.

Não foi incluída uma senha padrão. Não há formulário de cadastro público. A sessão vale por até oito horas; o botão **Sair** revoga o acesso dessa sessão. Reiniciar ou publicar uma versão nova exige entrar novamente.

## 6. Configurar Claude

Depois do login, entre em **Classificação → Configurar Claude / API**. Você pode digitar a chave para usar na execução atual do serviço.

Para mantê-la entre reinicializações, defina **BANCO_API_KEY** em **Variables do Railway**. As opções abaixo são adicionais:

| Nome | Uso |
| --- | --- |
| `BANCO_API_KEY` | Chave do fornecedor, carregada na memória ao iniciar |
| `API_MODELO` | ID exato do modelo Claude liberado para sua chave |
| `API_PROTOCOLO` | `anthropic` para a API oficial; `openai` para um fornecedor com esse protocolo compatível |
| `API_BASE_URL` | `https://api.anthropic.com` ou URL base fornecida pelo seu serviço |

Você também pode configurar modelo, formato e endereço no aplicativo, sem essas três variáveis adicionais. Se definir uma variável adicional, seu valor será reaplicado em cada início do servidor. Para a Anthropic oficial, ANTHROPIC_API_KEY continua disponível como alternativa ao BANCO_API_KEY.

Teste a conexão e comece com **25 questões pendentes**. A chave não volta à interface, não entra nos backups e não é gravada no banco. O consumo de hospedagem e o consumo da API são separados. Mais detalhes sobre a classificação: `GUIA_API_CLAUDE.md`.

## 7. Restaurar seu acervo local

Não envie o banco pessoal ao GitHub. Use um backup completo do Banco de Questões Local, criado em **Dados e backup → Criar e baixar backup**. Os backups das versões 1.0 a 1.3 são aceitos.

A restauração ocorre na inicialização, antes de atender o site, e preserva os dados atuais numa pasta do volume. Para transferir o ZIP, use a CLI do Railway:

1. Instale a CLI seguindo https://docs.railway.com/guides/cli. Se já usa Node.js, a instalação também pode ser feita pelo comando indicado nessa documentação.
2. Abra o PowerShell na pasta onde está o backup e execute:

```powershell
railway login
railway link
railway volume list
```

3. No vínculo, selecione o projeto, ambiente e serviço do banco. Anote o nome ou ID do volume conectado. Envie o seu arquivo para o nome reservado abaixo, substituindo VOLUME e o caminho local pelos seus valores:

```powershell
railway volume files --volume VOLUME upload "C:\caminho\seu_backup.zip" /backup_importar.zip
```

4. No Railway, pause lotes do aplicativo, adicione **RESTORE_ON_START=1** em Variables e faça **Deploy**.
5. Nos logs deve aparecer **Backup restaurado; dados anteriores preservados no volume**.
6. Abra o site, faça login e confira provas, categorias, respostas e histórico.
7. Remova a variável RESTORE_ON_START, ou mude para `0`, e aplique a alteração.

O arquivo recebido é validado antes da substituição. O ZIP aplicado é renomeado para `backup_importado_DATA_HORA.zip`, e a pasta anterior fica em `dados_antes_restauracao_DATA_HORA`. Se o backup for inválido, a publicação falha sem substituir o acervo; remova ou corrija o arquivo para tentar novamente. Seus arquivos pessoais ficam no volume, fora do código.

Se preferir começar com o banco vazio, basta entrar em **Provas e importação** e enviar PDFs pelo site. Para o primeiro teste, as duas provas de exemplo podem ser importadas por **Ler pasta provas_entrada**.

## 8. Conferir a publicação

- Sem estar autenticado, abrir o endereço do site deve mostrar a tela de login.
- Após entrar, importe uma prova e confira o PDF e as questões.
- Faça uma tentativa e baixe um backup.
- Reinicie o serviço e confirme que o acervo e o histórico continuam salvos.

Se aparecer **Configure ADMIN_USER / ADMIN_PASSWORD / SECRET_KEY**, confira os nomes e valores em Variables. Se aparecer **Conecte um volume**, confira o vínculo e Mount Path `/data`. Se mostrar **Host inválido**, confira o domínio ou TRUSTED_HOSTS. Se o navegador continuar voltando ao login, use o endereço HTTPS e confira as configurações do cookie.

## Limites desta entrega

O projeto tem **um acesso administrativo privado**. Não implementa contas de estudantes, separação de histórico por pessoa, cadastro público ou recuperação de senha por e-mail. Para trocar a senha, altere ADMIN_PASSWORD no Railway e publique a configuração.

Os testes locais incluem uma execução real com Gunicorn, login, proteção das APIs, persistência e restauração. A imagem Docker e a publicação na sua conta do Railway não foram executadas neste ambiente. A classificação pela API foi testada com fornecedor simulado, sem chave real.

Referências: https://docs.railway.com/guides/dockerfiles ; https://docs.railway.com/guides/monorepo ; https://docs.railway.com/volumes ; https://docs.railway.com/networking/domains/railway-domains ; https://docs.railway.com/cli/volume .
