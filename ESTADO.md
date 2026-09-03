# Estado do painel PCM — o que não está óbvio no código

**Última atualização: 28/08/2026.** Base escrita pelo Fabrício; ampliada com o que
foi descoberto e alterado em 19–24/08 — inclui o sentinela do Fracttal (§6d), a
grafia canônica de cluster (§3.1b) e as armadilhas novas da §6. Em 28/08 entrou a
regra do `novo.html` como fonte (§1, "Onde o código realmente mora").

> **Este arquivo não contém nenhuma credencial, senha ou token.** Eles vivem nos
> GitHub Secrets, nas app settings do Azure e no `.env` local, e passam por canal
> direto — nunca por arquivo ou e-mail. A seção 2 diz apenas **onde** cada um vive
> e **o que quebra** sem ele.

---

## 1. O que roda onde

### Na nuvem (GitHub Actions), sozinho

| Workflow | O que faz | Cadência REAL |
|---|---|---|
| `semanal.yml` | `atualizacao_semanal.py` + `gerar_pcm_json.py` + `gerar_etiquetas_json.py` → `banco_dados.json`, `etiquetas.json` | cron diz `*/15`; **medido: ~38 min** |
| `gestao-pcm.yml` | `gerar_gestao_pcm_json.py` → `gestao_pcm.json` | idem |
| `gestao-pcm.yml` (passo a incluir) | `gerar_engenharia_json.py` → `engenharia.json` | **ainda não roda na nuvem** — ver §3 |
| `azure-swa.yml` | deploy do painel no Azure SWA | ao fim de cada robô (ver §3) |

**Não confie no `*/15`.** Medição de 21/08, 12 execuções: intervalos de 28, 34,
29, 37, 44, 47, 56, 37, 43, 41 min — média **~38**. O GitHub descarta a maioria
dos agendamentos; `*/15` cai em `:00/:15/:30/:45`, os horários de pior fila.
Duração da execução: 5,5 a 6,4 min.

Quem precisar de atualização imediata: Actions → workflow → **Run workflow**
(`workflow_dispatch`), que não sofre o atraso.

### Na máquina do PCM, manual (PCM_Painel)

Nada agendado — se ninguém abrir o programa, não acontece:

| Botão | Script | Quando |
|---|---|---|
| Gerar Programação Semanal | `programacao_v7.py` | sexta, gera a semana seguinte |
| Enviar semana pra nuvem | `publicar_semana_github.py` | logo depois de gerar |
| Programação Semanal Clientes | `gerar_relatorio_cliente.py` | sexta, depois do time aprovar |
| Atualizar Gestão MPAS | `atualizar_mpas.py` | quando a Gerencial muda |
| Rodar Atualização Diária | `atualizacao_semanal.py` | durante a semana |

**A Gestão MPAS é o caso mais frágil:** a fonte é o `Gerencial - PCM_2026_R00.xlsx`
no OneDrive, que a nuvem não enxerga. Esse JSON só atualiza por ação manual.

### Confiabilidade — módulo de engenharia (03/09)

Tela `conf` no `novo.html` (seção **Engenharia** da barra), só admin/equipe
(`TELAS_ADMIN`); o `engenharia.json` já cai na rota `/*.json` → admin/equipe.
Dado: `gerar_engenharia_json.py` lê **todas** as `work_orders` do Fracttal (31 mil,
~6 min), fica com as Corretivas dos últimos 30 dias e escreve, por ativo: dimensões
A/B/D do Engenheiro Preventivo, nível, criticidade **proxy por família**
(`critProxy: true` — a matriz do cap. 4 do PCM Descomplicado nunca foi preenchida),
MTBF/MTTR/disp casados do `confiabilidade.json` por nome, e as OS com texto, tipo
e nota do técnico (alimentam o pré-preenchimento do FMEA).

**Serviço não é falha.** "Limpeza dos sensores" chega como Corretiva. O robô marca
`servico` por padrão no texto e a dimensão A conta só falhas; o ativo fica visível
com `soServico` para a engenharia reclassificar no Fracttal.

**Etapa 1 (hoje):** tickets e relatórios FMEA/Causa Raiz emitidos vivem em
`localStorage` (`pcm_conf_tickets_v1`, `pcm_conf_relatorios_v1`) — somem ao trocar
de navegador. Etapa 2: `/api/ticket` gravando JSON no repositório. Etapa 3: e-mail
por evento e por emissão pelo SMTP do `atualizacao_semanal.py`. O botão de
rascunho por IA do mockup **não subiu** — manda notas de OS para API externa; só
com aval.

O módulo foi gerado a partir de um mockup por `_integrar_novo.py` (sessão de
03/09) e **colado no `novo.html`; o HTML é a fonte**, como o resto. Classes têm
prefixo `cf-` porque `pill`, `at`, `hist`, `rel`, `cri`, `ruim` já existiam.
Cuidado ao editar: o `ligar()` do painel captura `[data-i]`, `[data-f]` e `.ftxt`
em toda a página — o módulo usa `data-ci`, `data-cff`, `data-cp` e `.cf-sel` para
não cair nesses handlers.

Achado do dado (03/09): a **disponibilidade agregada por cliente/usina** no
`confiabilidade.json` soma as falhas de todos os ativos e o MTBF encolhe com a
frota — Athon sai com 14%. Só o nível de ativo é honesto. A tela avisa; o ajuste
no robô que gera o arquivo está pendente.

### Onde o código realmente mora

Os scripts vivem no repositório. A pasta do OneDrive tem **shims** que delegam.
Editar o shim não tem efeito. **Se um deles passar de ~1 KB, alguém sobrescreveu
o shim com o arquivo real.** Conferido em 21/08: todos entre 921 e 942 bytes.

**O `novo.html` é fonte, não é gerado — edite ele direto** (28/08). Como todo
`.html` deste repositório.

Até 27/08 ele era montado por um `construir_novo.py` a partir de um
`side_pcm.html` + `montar.js` que **nunca estiveram aqui** — viviam numa pasta
temporária de sessão do Claude. Quem abrisse o repositório via só o arquivo
gerado e, com razão, editava ele. Foi o que aconteceu em 27/08 às 21h, com os
chips de semana (7d13ebfe): uma reconstrução teria apagado aquilo **sem aviso
nenhum**, porque o build reescreve o arquivo inteiro. Só não apagou porque o
`git` acusou conflito.

Esse gerador está aposentado. Não regenere o `novo.html`.

**Detector:** o arquivo tem que conter `_semanaEscolhida` e `trocarSemana` (os
chips de semana) e `_semPapel(_s.quem)` (a tela de conta sem papel). Se algum
sumir, alguém republicou por cima a partir de um build velho — recupere pelo
histórico em vez de refazer.

---

## 2. Credenciais — onde vivem e o que quebra sem elas

| Segredo | Onde vive | Quebra o quê |
|---|---|---|
| `FRACTTAL_CLIENT_ID` / `_SECRET` | GitHub Secrets, `.env` local **e app settings do SWA** ✅ | os robôs, e a escrita de motivo na OS |
| `PCM_MPAS_SENHA` | **só na cabeça de quem cifra** | regenerar o `mpas.json`; ver a armadilha em §6 |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | GitHub Secrets | o deploy |
| `AZURE_CLIENT_ID` / `_SECRET` | app settings do SWA | o login Microsoft inteiro |
| `ACESSOS_BLOB_URL_B64` | app settings do SWA | o cadastro de clientes (§4) |
| `LISTA_PRIORIDADES_B64`, `CONFIABILIDADE_B64` | GitHub Secrets | os robôs |

As planilhas de origem existem no OneDrive: `Lista_Prioridades_GridCo.xlsx` e
`Planilha Confiabilidade R00.xlsx`. Os dois Secrets são **reconstituíveis**.

**A senha do `mpas.json` é o único ponto único de falha real.**

---

## 3. O que está quebrado ou pendente

### Bloqueia uso

- **`engenharia.json` não se atualiza sozinho.** O passo do robô ainda não está no
  `gestao-pcm.yml` (meu PAT não tem escopo `workflow`). Até o Fillipe incluir o passo,
  o arquivo é o da última rodada manual (03/09 18:25). Ver o snippet no §3 abaixo.

**Nenhum item aberto** desde 21/08 17:15. Os três que bloqueavam foram fechados:
app settings do Fracttal, gatilho do deploy e acesso da equipe.

### Aberto, sem bloquear

**1. ~~Sincronização local quebrava o robô do `gestao_pcm.json`~~** — ✅ **RESOLVIDO
em 21/08 17:50.** Mantido aqui porque o mecanismo é instrutivo e pode se repetir.

> **Como terminou:** o Fabrício desabilitou a tarefa agendada. O robô voltou
> sozinho, sem nenhuma linha de código alterada — rodada das 17:43 concluída com
> sucesso, publicando às 17:50, a primeira do robô desde 15:54. Último push local:
> 17:02.
>
> A lição: **não era o robô que estava quebrado.** Era a interferência de um
> segundo publicador. Antes de mexer no que falha, vale perguntar quem mais
> escreve no mesmo lugar.

**O mecanismo, para quem encontrar algo parecido.** O robô `gestao-pcm.yml` falhava
no step 6 ("Publicar só se os dados mudaram"), esgotando as 5 tentativas com
`pull --rebase`. O step 5 (gerar via API) **passava** — só o push falhava.

Havia uma tarefa na máquina do Fabrício publicando o `gestao_pcm.json` a cada
15 min, com a identidade `fillipe.figueiro@gmail.com`. O que cada um tocava:

| Quem | Arquivos no commit |
|---|---|
| Máquina local | `gestao_pcm.json` |
| Robô da nuvem | `gestao_pcm.json` **e** `_gestao_pcm_published_hash.txt` |

O `_gestao_pcm_published_hash.txt` é o controle anti-churn:

```bash
NEW_HASH=$(hash do gestao_pcm.json recém-gerado)
OLD_HASH=$(cat _gestao_pcm_published_hash.txt)
if [ "$NEW_HASH" = "$OLD_HASH" ]; then exit 0; fi   # nada a publicar
```

Como a tarefa local sobrescrevia o JSON **sem atualizar o hash**, o robô sempre via
divergência e sempre tentava publicar, mesmo com dado idêntico — e aí colidia. A
interferência fazia duas coisas ao mesmo tempo: **anulava o anti-churn** e
**causava a colisão**.

**Por que quase passou despercebido:** enquanto a tarefa local publicava, o dado
chegava e a falha do robô não tinha consequência visível. Se aquela máquina saísse
do ar com a tarefa ainda agendada, a Gestão PCM congelaria sem erro em lugar nenhum.

**Se reaparecer:** procure um segundo publicador antes de mexer no robô. E note que
desligar a máquina não bastaria — tarefa agendada em máquina sem dono volta a
quebrar quando a máquina voltar.

**1b. Grafia canônica de cluster** — ✅ **resolvido em 21/08 no código.**

Três clusters tinham duas grafias no cadastro do Fracttal (`PA LESTE 01`, `PA NORTE 01`,
`MA LESTE 02`), e o sistema os tratava como equipes diferentes. Efeito: **297 tarefas sem
destinatário de alerta** e capacidade partida ao meio — `PA Leste 01` aparecia como
8,4 h *e* 46,5 h das mesmas 44 h.

Origem: no Fracttal cada cluster tem duas entradas na "Ativo Classificação 2" — uma para
instalação (tipo 1), outra para equipamento (tipo 2). Nessas três, a segunda foi digitada
em caixa alta. Por isso a divisão era limpa: instalações numa grafia, equipamentos na outra.

**Decisão:** corrigir no código, não no cadastro. A API do Fracttal **só lê** classificação
— não há endpoint de update (sondado em 21/08, ver abaixo). A interface exigiria três
renomeações manuais, e o cadastro é território de outra rotina.

O `gerar_pcm_json.py` ganhou `_cluster_norm()` (mapa canônico, silencioso) e
`_conferir_clusters()` (alarme só para grafia **nova**, já entregando a linha a colar).
Detalhes em `A1_Normalizacao_Cluster.md`.

> **Por que o log é silencioso para os casos conhecidos:** a primeira versão gritava a cada
> normalização, para pressionar pela correção na origem. Como a origem não será corrigida,
> isso viraria três linhas por rodada que ninguém atenderia — e aviso que ninguém atende
> ensina a ignorar avisos, inclusive os que importam.

**Efeito colateral esperado:** `PA Leste 01` passa a mostrar **54,9 h de 44** — estourado.
Não é o conserto piorando; é o número verdadeiro aparecendo. A divisão escondia uma equipe
25% acima da capacidade.

**Ficou pendente no cadastro**, se um dia alguém for mexer: ids 253625, 247469 e 255525;
mais `TESTE` (252610/252611), que traz 2 tarefas ao painel.

### Escrita no Fracttal: a REST não serve, e o RPC exige token de usuário

Sondado em 21/08. A REST pública (`app.fracttal.com/api/`) é **só leitura**. A escrita vai
por **JSON-RPC** em `one.fracttal.com/rpc/proxy`, com `Origin` forjado — é como o App de
Campo fecha OS.

Mas o RPC exige **token de usuário** (`authorization_code`, as credenciais
`FRACTTAL_OAUTH_*`). O token de leitura (`FRACTTAL_JWT_TOKEN`, client_credentials) leva
**HTTP 401 com corpo HTML**.

> Detalhe útil para diagnóstico: **401 com HTML = porta fechada** (gateway recusou antes de
> resolver o método). **Erro em JSON** = método errado. Dá para distinguir os dois casos
> pelo formato da resposta, sem adivinhar.

O script `sondar_rpc_fracttal.py` fica pronto na pasta do projeto: se um dia houver token
de usuário à mão, é rodar. Nenhum dos 26 métodos que o middleware usa é de `inventories`,
então os nomes desse módulo continuam desconhecidos.

**2. Passo 4 — desligar o GitHub Pages.** O `github.io` serve `banco_dados.json`
(4,07 MB) **sem autenticação nenhuma**. Enquanto estiver de pé, toda a proteção do
Azure convive com uma porta aberta ao lado. Já causou um falso positivo em teste
de acesso (§6).

**3. `mpas.json` publicado em claro** no repositório público, com observações em
texto livre incluindo nota de pessoal. O gerador foi corrigido para falhar
fechado, mas **cifrar hoje tranca a aba para todos** — ver §6.

**4. Dois `azure-swa.yml`.** O que roda (`.github/workflows/`) e o molde
(`_azure/`). O molde tem cabeçalho avisando, e **o aviso não impediu duas edições
no arquivo errado em 21/08**. Recomendação: apagar o molde; o git guarda.

### Conhecido e deliberadamente não tratado

**1.059 tarefas abertas dentro de OS com status Finalizados.** É problema de
cadastro, não de programação. O filtro de topo do motor as exclui de propósito.
Decisão do PCM: fora de escopo.

---

## 4. Autenticação e acesso — como funciona hoje

Desde 20/08 o painel **não usa mais convites**. A cada login, o Azure chama
`/api/papeis` (`rolesSource`) e usa o que ela devolver.

### A regra

| Quem | Recebe |
|---|---|
| Tenant da Grid, não-convidado | `admin` |
| Convidado B2B no tenant da Grid | tratado como externo |
| E-mail no cadastro, para exatamente um cliente | `cli-<cliente>` |
| Qualquer outro | nenhum papel |

**Decisão registrada (19/08, Fillipe):** todo o tenant da Grid recebe `admin`.
Consequência aceita: qualquer área lê a operação de todos os clientes e enxerga
as quatro abas internas (Religamentos, Em Verificação, Sugestões IA, Gestão MPAS).
O que se ganha é atrito zero e **offboarding automático** — conta desativada no
tenant perde acesso sozinha.

### O papel-sentinela `vivo`

Sai em **todo** login que passa pela função, inclusive para quem não recebe papel.
É inerte: nenhuma rota o referencia.

| No `/.auth/me` | Significa |
|---|---|
| `["admin","vivo",…]` | tudo certo |
| `["vivo"]` sozinho | a função rodou e **decidiu** não dar papel → cadastro |
| **sem `vivo`** | a função **não rodou** → é bug, não convite |

Existe porque **o `catch` do runtime em volta da chamada do `rolesSource` é vazio**
(achado do Fabrício): se a função quebrar, o login continua funcionando e a pessoa
entra com zero papéis — sintoma idêntico ao de quem não foi convidado. Sem o
sentinela, quem investigar procura um convite em vez de um bug.

### Cadastro de cliente

Tela em **`/acessos.html`**, restrita a `admin`. Grava num JSON no Blob
(`stgridcocampomw`, container `acessos`) — **fora do repositório**, porque são
e-mails de pessoas e o repositório é público.

Conta `@gridco.com.br` **não pode** ser cadastrada como cliente: a tela recusa. A
regra do tenant vence antes de olhar o cadastro, então a linha existiria sem fazer
nada — e alguém confiaria nela.

Gravação com `If-Match` no ETag: duas pessoas cadastrando ao mesmo tempo não se
sobrescrevem.

**Validado em 21/08:** cadastro de um e-mail externo, login com ele, e a visão restrita
ao cliente escolhido — o caminho ponta a ponta funciona.

**Falta:** o link no menu do painel (`index.html`). Até lá, acessa-se pelo
endereço direto.

---

## 5. Decisões que o código aplica e que não se deduzem lendo

### A regra de ouro

**Status da OS ≠ Estado da Tarefa.** Concluído é `Estado da Tarefa == 'Finalizada'`,
**nunca** o status da OS. Existe OS `Finalizados` com tarefa aberta e o contrário.
Todo cálculo de conclusão usa o estado da **tarefa**.

### Fila de reprogramação entre semanas (21/08)

Tarefa vencida volta para a semana seguinte, com regra por sigla:

- `MPM`, `MPW`, `MPQ`, `MPT` → **só do mês corrente**
- `MPS`, `MPA` → de qualquer mês (semestral/anual atrasada continua valendo)
- Corretiva e Inspeção → **sempre**
- Handover e Administrativa → **nunca**
- Religamento → já excluído pelo motor

Regra que originou tudo: **MPM do mês corrente nunca pode ficar invisível** — ou
está na semana, ou aparece em "Não couberam na semana". Ligada por `PCM_FILA`
(padrão ativo).

### O pin manda (21/08)

Observação com dia é **ordem**, não sugestão. Se o dia pedido está cheio, o motor
força marcando `[EXCEDE HH]`, em vez de mandar para pendentes.

Ao implementar isso descobriu-se que **o `force` do `alloc_diurno` nunca forçou**:
pulava as guardas de entrada e era barrado nas de saída (`effective_min` truncava
para a capacidade restante, zero num dia cheio). A corretiva "forçada" só entrava
quando ainda havia capacidade — ou seja, quando não precisava forçar. Corrigido.

### Rolagem do dia

`ROLAGEM_MODO_DEFAULT = "ativo"` desde 21/08. **Ficou em sombra desde que foi
escrita** — registrava o que rolaria e nada se movia, e ninguém percebeu, porque
sombra não faz barulho. Trata o **dia**; o que atravessa a **semana** é a fila
acima.

### Escrita no Fracttal (`/api/motivos`)

`PUT /work_orders/{WO_FOLIO}` com `{"note": <texto completo>, "account_code": "02"}`.

Quatro armadilhas:
- o path é o **folio**, não o `id_work_order`
- `account_code` é código de **pessoa** (02), e a alteração fica atribuída a ela
- **valor vazio é recusado** — não dá para limpar pela API
- só grava em OS **em processo** ou **em revisão**

A escrita **substitui o campo inteiro** — não existe append. Por isso é
ler → concatenar → gravar, **relendo imediatamente antes do PUT** para não
atropelar quem edita pela tela.

Duas linhas do mesmo dia para a mesma tarefa são permitidas de propósito: a tarefa
pode não ter sido feita por dois motivos.

### Decisão 28, reescrita (19/08)

Deixou de ser "privar o repositório" e passou a ser **"tirar o dado do
repositório"** (opção 3). Motivos: privar não resolve a cota do Actions; e runner
self-hosted em repositório público é inseguro — fork abre PR e o workflow roda na
sua máquina. O `AUXILIAR - FABRICIO.xlsx` entra na mesma mudança.

**Números da cota, medidos em 21/08** (a estimativa anterior de ~47.700 min/mês
partia do cron declarado, não do real):

| | Estimado | Medido |
|---|---|---|
| Execuções/dia | 96 | **~38** |
| Duração | 8,9 min | **~6,0 min** |
| **Total/mês, 2 workflows** | ~47.700 min | **~13.700 min** |

A decisão não muda — 13.700 continua ~7× acima dos 2.000 gratuitos.

### Filtro por papel é lista de PERMISSÃO

Em `api/dados/index.js`, **só os campos explicitamente copiados** saem para o
cliente. **Nunca trocar por um spread do objeto** — seria o caminho para vazar um
bloco novo sem ninguém perceber.

Mesmo princípio na config: `{"route":"/*.json","allowedRoles":["admin","equipe"]}`
faz arquivo novo **nascer fechado**. Antes eram sete entradas nominais com porta
larga no fim, e dois arquivos de dados caíam nela.

---

## 6. Armadilhas — coisas que falham em silêncio

Esta seção existe porque **é a classe que mais custou tempo neste projeto**. Todas
já cobraram pelo menos uma vez.

### `az ad app create` nasce com `enableIdTokenIssuance: false`

O EasyAuth do SWA usa fluxo híbrido e pede `code id_token`. Sem emissão de ID
token, o **login entra em laço** — sem mensagem de erro, sem tela de acesso
negado. Parece problema de senha.

```
az ad app update --id <APP_ID> --enable-id-token-issuance true
```

Efeito imediato, sem deploy.

### `GITHUB_TOKEN` não dispara workflows

O robô faz `git push` com o token padrão do `actions/checkout`, e **o GitHub não
dispara workflows a partir de pushes feitos com ele** (proteção contra laço).

Consequência: o `on: push` do `azure-swa.yml` **nunca funcionou** para as rodadas
do robô, desde 19/08. O dado atualizava no repositório e o Azure ficava para trás.
Os deploys que pareciam do robô vinham, na verdade, dos commits da máquina local
(token pessoal, que dispara).

Corrigido em 21/08 com `workflow_run`, que dispara ao **fim** de cada robô.
Confirmado às 17:09:41 com um deploy automático bem-sucedido.

> `workflow_run` casa pelo campo **`name:`** do workflow, não pelo arquivo. Um
> acento fora do lugar e ele nunca dispara, em silêncio. Os nomes válidos são
> `"Atualiza Programação Semanal (a cada 15 min)"` e
> `"Atualiza Gestão PCM (a cada 15 min)"`.

### O `az` no Windows trunca valores com `&`

O `az` é um `.cmd`; o `cmd.exe` reinterpreta o argumento e os `&` viram
separadores de comando. Em 19/08 a gravação de uma URL com SAS **respondeu 200 e
guardou 89 de ~230 caracteres**.

Solução adotada: gravar em **base64** (`ACESSOS_BLOB_URL_B64`), cujo alfabeto não
tem `&`. O `_acessos_store.js` também recusa URL com `?` e sem `sig=`, em vez de
tentar usar.

**Sempre conferir o comprimento do que foi gravado** contra o comprimento da
origem.

### Cifrar o `mpas.json` hoje tranca a aba para todos

A senha de decifra vem da **tela de senha legada** (`js/app.js:359`:
`if(S.isAdmin){ sessionStorage.setItem('gc_mp_k', s); }`), e o `js/auth.js` diz
que com papel `admin` **a tela de senha some**.

Com o login Microsoft, ninguém digita senha → `gc_mp_k` nunca é preenchido →
`js/app.js:1174` não acha a chave → mostra o cadeado e "conteúdo protegido".
**Sem erro. Para todo mundo.**

**Resolvido em 24–25/08:** o cadeado agora pede a senha na própria aba, uma vez
por sessão. Mas a resolução expôs a armadilha seguinte:

### `setx` não muda programa aberto — e a cifra herda a senha errada

Em 24/08 o `mpas.json` foi publicado cifrado com uma senha que **não decifrava
mais**: `InvalidTag` até para a `PCM_MPAS_SENHA` correta do registro. Causa:
`setx` grava no registro, mas **processos já abertos continuam com o ambiente
antigo** — o PCM_Painel aberto desde antes da troca cifrou com o valor velho, e
nada falhou, porque para o gerador a senha presente é a senha certa.

Sintoma: a aba recusa a senha "certa" e todo mundo desconfia de quem digita.
Diagnóstico que funciona: **testar a decifra localmente** contra o pacote
publicado (PBKDF2 + AES-GCM com salt/iter do próprio pacote) usando a senha lida
do registro — se falhar ali, o problema é o pacote, não o dedo. Correção: fechar
e reabrir o programa (ou injetar a senha do registro no ambiente do subprocesso)
e republicar. Feito em 25/08; decifra conferida contra o `origin/main` antes de
avisar que estava no ar.

### O GitHub Pages produz falso positivo em teste de acesso

O `github.io` serve os mesmos arquivos **sem autenticação**. Em 19/08 um teste de
acesso "passou" porque o download veio de lá, não do SWA.

**Todo teste de acesso precisa confirmar o host na barra de endereço.** Some
quando o passo 4 acontecer.

### Dois arquivos com o mesmo nome

`_azure/azure-swa.yml` (inerte) e `.github/workflows/azure-swa.yml` (o que roda).
Em 21/08 duas edições seguidas foram para o inerte, apesar do cabeçalho em caixa
alta avisando. **O aviso não impediu.**

Para editar o certo, use a URL direta:
`https://github.com/<owner>/<repo>/edit/main/.github/workflows/azure-swa.yml`

### `/.auth/me` não provoca login

Ele **relata** a sessão atual. Aberto numa janela anônima devolve
`{"clientPrincipal": null}` — o que parece falha e é só ausência de sessão. Para
testar: ir na **raiz** primeiro (que redireciona para o login) e só depois abrir
o `/.auth/me`.

---

### ⚠ O `etl_list` do Fracttal devolve credenciais em texto puro

**Achado em 22/08.** Duas rotas da API expõem o mesmo segredo com proteções diferentes:

| Rota | O campo `private_key` |
|---|---|
| `inventories`… `integrations_connections_list` | mascarado — `'*******************'` |
| `etl_list` | **em texto puro, completo** |

Ao listar os registros ETL veio a chave privada inteira da conta de serviço do Google
(`medidores@healthy-dolphin-477218-e4…`) e o `client_secret` da conexão Fracttal API.

**Consequência prática:** qualquer integração que leia ETL — inclusive o conector MCP —
recebe credenciais que a plataforma acredita estar protegendo. Quem auditar o acesso pelo
endpoint de conexões vai concluir, erradamente, que os segredos estão mascarados.

**Ação tomada / pendente:**
- Rotacionar a chave da service account no Google Cloud (projeto
  `healthy-dolphin-477218-e4`), atualizar a conexão no Fracttal e revogar a antiga
- Reportar ao suporte do Fracttal: mascarar num endpoint e não no outro é falha da
  plataforma, não configuração nossa

**Regra que fica:** antes de listar ETL — ou qualquer objeto de integração — assumir que
pode vir credencial junto. Não colar a saída em canal persistente sem olhar.

## 6b. Latência: quanto demora uma mudança a aparecer no painel

Medido em 22/08. O gargalo **não é processamento** — é fila.

| | |
|---|---|
| Motor rodando (os 3 scripts) | **6 min** |
| Esperar o cron acordar | **até 57 min**, média 38 |
| **Total até o painel** | **até ~63 min** — 90% espera |

Detalhe por passo do `semanal.yml` (364 s de 384 s num passo só):

```
  364.0s  Rodar o motor semanal      ############################################
    9.0s  Instalar dependências      #
    2.0s  Baixar o repositório
    2.0s  Publicar
```

Otimizar o workflow economizaria 10 s de 384. O `gerar_pcm_json.py` já usa
`load_workbook(read_only=True, data_only=True)`, que é o caminho rápido do openpyxl.

### O que foi feito: gatilho por `push` (22/08)

O `semanal.yml` só tinha `schedule` e `workflow_dispatch`. Publicar uma
`Programação Semana XX.xlsx` não disparava nada — o arquivo esperava o cron.

Acrescentado:

```yaml
  push:
    branches: [main]
    paths:
      - "Programa*.xlsx"          # sem acento no padrão, de propósito
      - "Observacoes_Semana*.txt"
      - "AUXILIAR - FABRICIO.xlsx"
```

Publicar a semana ou ajustar um pin passa a disparar **na hora**: ~63 min → ~6 min.

O histórico justifica: a Semana 35 foi publicada **três vezes em 21/08** (10:59, 14:01,
14:55) pelo botão do PCM_Painel. Não é evento de sexta.

> **Não cria laço**, por duas razões independentes: o robô commita com `GITHUB_TOKEN`
> (que não dispara workflows), e o que ele publica — `banco_dados.json`, `etiquetas.json`
> — não está no `paths`. **Não cria corrida**: o `concurrency: group: semanal` já enfileira.
>
> Mudança de **código** não dispara, de propósito: senão cada commit custaria 6 min.

**Cuidado ao editar este arquivo:** o `name:` dele é o que o `azure-swa.yml` casa no
`workflow_run`. Um caractere diferente e o deploy automático para em silêncio.

### O que NÃO é resolvido pelo push

O gatilho reage a **arquivo que muda no repositório**. O que acontece no Fracttal — técnico
fechando OS, reprogramação — só chega quando o robô consulta a API:

| O que muda | Dispara na hora? |
|---|---|
| Republicar a Programação Semanal | ✅ |
| Ajustar observação/pin | ✅ |
| Técnico fecha OS no Fracttal | ❌ espera o cron |
| Reprogramação no Fracttal | ❌ espera o cron |

## 6c. Webhook do Fracttal — existe, e por que ainda não usamos

Investigado em 22/08. **O Fracttal tem webhook**, por dois recursos combinados:

**Integrações → conexão tipo HTTP** (`id_type = 2`): URL livre, método
`get/post/put/delete`, e nove modos de autenticação — `NoAuth`, `Basic`, `OAuth2`,
`BearerToken`, `CustomToken`, `CustomHeaders`, `CustomSession`, `OAuth1`, `SAP`.

**Dispatcher**: regras *evento → condição → ação*. Já em uso — três regras, duas ativas,
em `NEW_WORK_ORDER` e `NEW_WORK_REQUEST`. E há uma conexão configurada (Google Sheets
service account, "Criação de Medidores"), o que prova que o recurso está habilitado no
plano.

Eventos relevantes para o painel:

```
WO_TASK_FINISHED (61)          ← a regra de ouro: Estado da Tarefa = Finalizada
WO_TASK_STARTED (67)
REASON_TASK_PAUSED (62)
EVENT_WORK_ORDER_FINISHED (7)
EVENT_WORK_ORDER_IN_REVIEW (2)
WO_RESPONSIBLE_CHANGE (64)
```

### Por que a forma óbvia não serve

Fracttal → `POST` no `repository_dispatch` do GitHub → robô roda. Parece limpo, e é
armadilha: na Semana 34 foram **723 tarefas finalizadas em 5 dias**, ~145/dia. A 6 min por
rodada, **14 horas de execução por dia** — muito pior que o cron.

E o `concurrency` não salva: com `cancel-in-progress: false` tudo enfileira; com `true`,
numa rajada de fechamentos às 17h cada evento cancela o anterior e a rodada nunca termina.

### PARADO em 22/08 — o Fracttal não tem "webhook", tem ETL

Três das quatro peças foram construídas e **provadas**. A quarta esbarrou no modelo do
Fracttal, que é diferente do que eu supus.

**O que ficou pronto e testado:**

| Peça | Estado |
|---|---|
| `repository_dispatch: types: [fracttal-mudou]` no `semanal.yml` | ✅ no ar |
| `GITHUB_DISPATCH_TOKEN` e `FRACTTAL_WEBHOOK_SEGREDO` nas app settings | ✅ |
| Amortecedor `api/fracttal` no SWA | ✅ 8/8 nos testes |
| Disparo real ponta a ponta | ✅ robô acordou 22/08 19:51 com origem `repository_dispatch` |

**Onde parou.** Para o evento `EVENT_WORK_ORDER_IN_REVIEW`, as ações que o dispatcher
oferece são:

```
SEND_EMAIL_TO · SEND_MAIL_TO_RESPONSIBLE · SEND_MAIL_TO_NOTIFICATIONS_GROUP
AUTO_FINISH_WO · ETL_EVENT
```

**Não existe ação "chamar HTTP".** A única que sai do Fracttal é `ETL_EVENT` — e ETL é um
pipeline `source → transform → target`, onde ambas as pontas são conexões com uma
`feature`. O único ETL existente lê uma planilha do Google e **escreve dentro do Fracttal**
(`feature: create_meters`): é ferramenta de importação.

Para o nosso caso precisaria do inverso — evento como origem, a nossa URL como destino — e
**não está confirmado** que exista uma `feature` de escrita HTTP genérica. Descobrir exige
montar um ETL de teste com mapeamento de campos.

**Estimativa corrigida:** eu descrevi como "criar uma conexão e uma regra". É montar um
pipeline ETL. Bem mais que um ajuste.

### Também descoberto: `WO_TASK_FINISHED` não está disponível

O evento existe no enum (id 61), mas **não é oferecido** em nenhum submódulo de Tarefas
(conferido em WORK_ORDERS=4 e PENDING_TASKS=3). O mais próximo de "trabalho executado" que
dá para assinar é `EVENT_WORK_ORDER_IN_REVIEW`.

Isso importa para qualquer automação futura: a regra de ouro (conclusão = Estado da Tarefa)
**não tem evento correspondente** no dispatcher.

### O que fica valendo

O **gatilho por `push`** (§6b) já resolve o caso que originou tudo: a Programação Semanal
aparece em ~6 min em vez de ~63.

O que continua sem solução é mudança feita **dentro do Fracttal**, que segue esperando o
cron — até 38 min. As três peças construídas ficam prontas para o dia em que houver um
caminho de saída do Fracttal.

### O desenho original, para retomada

Se um dia o caminho existir, era este — e o amortecedor já está construído:

```
Fracttal (WO_TASK_FINISHED)
      ↓ HTTP POST (conexão tipo 2 + regra no dispatcher)
middleware  /api/fracttal/mudou      ← só anota "tem novidade"
      ↓ no máximo 1x a cada N min, e SÓ se houve mudança
GitHub  repository_dispatch
      ↓
semanal.yml  (+ `repository_dispatch: types: [fracttal]` nos gatilhos)
```

Ganha nos dois sentidos: mais rápido quando há novidade, e **zero execução** quando não há
— hoje o cron roda de qualquer jeito.

**Custo:** uma rota nova no middleware, a lógica de amortecimento, um token do GitHub
guardado lá, e a regra no dispatcher. É projeto, não ajuste.

## 6d. O sentinela — como o painel reage ao Fracttal (NO AR desde 24/08 01:15 UTC)

A seção 6c descartou o dispatcher do Fracttal (as ações são e-mail/ETL; não há "chamar
URL"). O que entrou no lugar foi um **timer no middleware** — e o caminho completo está
provado em produção:

```
Fracttal  ←(3 chamadas leves, a cada 3 min)—  sentinela (timer no gridco-campo-mw)
                                                  │ impressão digital mudou?
                                                  ▼
                                        /api/fracttal (amortecedor no SWA, janela 10 min)
                                                  ▼
                                        repository_dispatch → semanal.yml → painel
```

**A impressão digital**: `total geral | total status 1 | total status 2` de work_orders —
o mesmo `total` que o `fonte_bd_api.py` usa para particionar. Criação de OS, término,
decisão de supervisor e cancelamento mexem nesses números. Custo: ~1.400 chamadas
leves/dia contra um teto de 200/min.

**Latência**: mudança no Fracttal → painel em ~3–13 min (antes: até 57). Sem mudança
(madrugada, fim de semana), zero rodadas por este caminho. O cron continua como rede.

**Onde mora cada peça**:

| Peça | Onde |
|---|---|
| `sentinela_painel` (timer 3 min) | fim do `function_app.py` do middleware |
| Estado (impressão digital) | Table `pcmsentinela` no storage do middleware |
| Amortecedor | `api/fracttal/` no repositório do painel |
| Segredo compartilhado | `FRACTTAL_WEBHOOK_SEGREDO` nas app settings do SWA **e** do middleware |
| Token do GitHub | `GITHUB_DISPATCH_TOKEN` no SWA (fine-grained, só este repo, Contents RW) |

**Regra que garante que nada se perde**: o sentinela só grava a impressão nova quando o
amortecedor responde `disparado`. Se responder `agrupado` (janela aberta), não grava — o
tick seguinte revê a mesma diferença e re-tenta até passar.

**Primeiro disparo real**: 24/08 01:15:06 UTC, rodada `repository_dispatch` concluída.
Para o disparo acontecer, cada elo teve que funcionar — timer, chamadas ao Fracttal,
Table, segredo, GitHub.

### Armadilha nova para a §6: o zip do middleware perde pastas

O `deploy_azure.ps1` lista os arquivos do zip UM A UM. Dois já ficaram de fora:

- `gestao.html`/`gestao2.html` — pego ANTES do deploy (as rotas morreriam com
  "gestao.html ausente")
- `chamado_garantia/` — pego DEPOIS: o deploy de 24/08 removeu o pacote de produção por
  ~1 h, e o `/health` acusou (`chamadoGarantia.ok=false`). O próprio código avisa: essa
  mesma falha já tinha matado a tela de chamados por 3 releases no passado.

Os dois estão na lista agora. **Ao criar arquivo/pasta novos que o `function_app.py` lê
do disco, acrescente ao `$files` do script no mesmo commit.** A conferência é:

```
grep -oE 'os\.path\.join\(os\.path\.dirname\(__file__\), "[^"]+"' function_app.py
```

tudo que sair daí tem que estar no `$files`. E o deploy pelo script pode estourar o
timeout de 300 s do az com o build remoto — status no cliente NÃO é status no servidor:
confira o `/health` depois, e se a mudança não assentou em ~6 min, o deploy não veio
(re-rodar resolve; um retry com `--timeout 540` passou de primeira).

## 6e. O dia 24/08 — quatro falhas silenciosas e o que ficou de regra

Um dia inteiro de consertos, e o padrão se repetiu: **tudo parecia funcionar.**
Cada um destes tinha alguma forma de sucesso aparente por cima.

### 1. O laço de publicação que não podia se recuperar

**Sintoma:** duas rodadas do `semanal.yml` falharam no passo Publicar — 22/08 19:56
e 24/08 01:16. Duas em 60. As duas logo depois de uma rodada por
`repository_dispatch`.

**Causa, reproduzida num repositório git de mentira:** quando duas rodadas se
cruzam, a segunda parte de um SHA anterior ao commit da primeira, regenera o JSON
com outro `geradoEm`, e o rebase conflita nessa linha. O `|| true` engolia a falha
e deixava **HEAD desanexado com arquivos não mesclados**. As quatro tentativas
seguintes batiam em `Pulling is not possible because you have unmerged files` —
engolidas pelo mesmo `|| true`. Cinco voltas, exit 1.

E o dado mais novo, o da segunda rodada, era **perdido** até a rodada seguinte.

**Conserto (no ar desde 02:09):** não rebasear. Cada tentativa faz `fetch` +
`reset --hard origin/main`, recoloca os arquivos gerados por cima, commita e
empurra. Conflito deixa de ser possível — não é tratado, é estruturalmente
inexistente.

> Sutileza que o conserto evita: durante um rebase, `ours` é o upstream e
> `theirs` é o seu commit. A inversão engana, e resolver "a favor de ours"
> descartaria justamente o dado novo.

**Resultado:** 16 rodadas nas horas seguintes, 16 sucessos — incluindo três pares
que se cruzaram com 3, 5 e 7 minutos de intervalo.

Patch e testes em `_azure_rolessource/patches_semanal/`. O teste só vale porque o
script ANTIGO falha nele: um teste que passa nos dois não provou nada.

### 2. A aba MPAS que sumiu da Gerencial

**Sintoma:** `atualizar_mpas.py` morria com
`ValueError: not enough values to unpack (expected 2, got 0)`.

**Causa:** a Gerencial foi reestruturada. A aba `MPAS` foi fundida em
**"Zeladoria e MPAS"**, o cabeçalho subiu da linha 4 para a 1, e a aba passou a
trazer 140 linhas de zeladoria misturadas com as de manutenção.

**O que isso expôs, e é o mais instrutivo:**

- O `except` do `_remapear_colunas` devolvia `{}` onde quem chama esperava uma
  dupla. **O plano B escrito para degradar com elegância derrubava o script** — e
  rodou pela primeira vez naquele dia, desde que foi escrito.
- Índices herdados apontariam para **outra coluna**: `C_MOD=7` pousaria em
  "Relatório enviado ao cliente" e gravaria esse texto no campo "módulos", sem
  erro nenhum. Por isso coluna perdida agora vira `None`, em vez de ficar com o
  índice velho.
- O `_enriquecer()` tinha o **seu próprio** `wb["MPAS"]` e o seu próprio recorte
  de linhas. Escapou do primeiro conserto porque procurei os pontos em vez de
  varrer todos — e quebrou depois, em produção.
- O `_enriquecer` parea **por posição** (`brutos[i]` com `manut[i]`). Sem o filtro
  por tipo seriam 312 linhas contra 172 coletadas, e cada observação cairia num
  registro diferente.

**Regra que fica:** ao adaptar leitura de planilha, varrer TODAS as referências
literais à aba e a índices de linha antes de consertar qualquer uma.

**O que a Gerencial nova não alimenta mais** (o conserto garante vazio, não
errado — mas se esses campos importarem, a correção é na planilha):

```
campo             19/08          hoje
modulos      219/219 100%    0/172   0%   ZEROU
termino       24/219  10%    0/172   0%   ZEROU
supervisor   219/219 100%    0/172   0%   ZEROU
apoio         18/219   8%    0/172   0%   ZEROU
obs          118/219  53%   18/172  10%
```

Total de 219 para 172 registros: as MPAs caíram de 111 para 59, e não estão em
nenhuma outra aba. Patch e 28 testes em `_azure_rolessource/fix_aba_mpas/`.

### 3. O OneDrive que aceita a escrita e depois a descarta

**Sintoma:** a biblioteca `Grid Co. - Gridco` saiu da lista de sincronização do
OneDrive. 48 arquivos da pasta viraram **placeholders órfãos** — metadados sem
provedor, ilegíveis por qualquer programa, inclusive em modo binário. O erro é
`O provedor do arquivo de nuvem não está em execução`.

O processo do OneDrive estava **rodando** o tempo todo. Só a biblioteca havia
saído do registro, em
`HKCU:\SOFTWARE\Microsoft\OneDrive\Accounts\Business1\ScopeIdToMountPointPathCache`.

**A parte perigosa:** durante a janela, escrever arquivo NOVO na pasta funcionava
— testei e passou. O que não funcionava era **persistir**. Quando a sincronização
religou, o OneDrive reconciliou e a nuvem venceu: os patches aplicados às 09:25
sumiram sem aviso, e o script voltou a falhar com o erro original.

> **Um ambiente que aceita a escrita e depois a descarta é pior que um que
> recusa.** Se a sincronização estiver instável, não edite nada nessa pasta.

**Como detectar um placeholder:**

```powershell
$i = Get-Item -LiteralPath $arquivo -Force
if (($i.Attributes -band 0x400000) -ne 0) { "somente-nuvem" }
```

Comparar com a máscara, não com texto: o `.Attributes.ToString()` devolve o
número cru (4199968) quando há flags que ele não sabe nomear.

**Resolvido** reiniciando o OneDrive — mas demorou mais de 50 segundos para
religar, tempo suficiente para eu declarar falha cedo demais.

### 4. Os hashes de senha publicados

**Sintoma:** nenhum. Estava assim desde sempre.

A linha 11 do `index.html` publicava os **hashes SHA-256 das senhas do admin e
dos 12 clientes**, sem sal e sem iteração, num repositório público.

**Por que não era catastrófico:** no SWA o caminho da senha já estava desarmado —
os `.json` exigem papel, o `loadDB()` falha para quem não tem, e o `doLogin()`
desiste antes de olhar a senha. Mas a cópia do **GitHub Pages não tinha portão
nenhum**: lá o painel rodava inteiro, com o cadeado e a chave no mesmo arquivo.

**Cortado em 24/08** (decisão 28, último passo): bloco `gc-pwds` removido, tela
de senha substituída pelo botão da Microsoft, Pages desligado.

Detalhe que quase derrubou o painel: a linha 35 do `app.js` era um `JSON.parse`
de topo sobre o elemento `gc-pwds`. **Sem o elemento ela lança, e o app.js inteiro
deixa de carregar.** Por isso os dois arquivos vão sempre juntos.

⚠ **Os hashes ficam no histórico do git para sempre.** Se alguma dessas senhas
for reaproveitada em outro lugar, precisa ser trocada lá.

---

## 6f. Saída do OneDrive: o caminho Graph (em construção)

O incidente acima motivou tirar as planilhas da dependência de uma estação estar
ligada e sincronizada. O TI provisionou em 24/08:

| | |
|---|---|
| Site | `https://gridcobr.sharepoint.com/sites/pcm-bd` ("PCM - Base de Dados") |
| Biblioteca | `Dados PCM` |
| Client ID | `ab7e21ac-17ba-48f8-a03c-c636673e48b6` |
| Permissão | `Sites.Selected` (aplicação) + **write** neste site |
| Autenticação | **certificado** (.pfx), thumbprint `AD1526BF...751`, vence em 2 anos |

**Por que `Sites.Selected` e não `Sites.Read.All`:** a permissão sozinha não dá
acesso a nada. Um administrador autoriza biblioteca por biblioteca. É chave de
uma porta, não chave-mestra.

**Por que write, se a Gerencial é só leitura:** o TI concedeu write por uma
leitura equivocada do pedido — achou que a rotina escrevia na Gerencial, que na
verdade é aberta com `read_only=True` em todos os pontos. Mas a conclusão está
certa por outro motivo: `programacao_v7.py` escreve o `Historico_Programacoes.xlsx`
e `atualizacao_semanal.py` escreve o BD. **Se a auditoria perguntar, a
justificativa verdadeira é essa.**

**O módulo** está em `_azure_rolessource/graph_planilhas/`, 20 testes passando.
Duas escolhas que o definem:

- **Não cai para o arquivo local quando o Graph falha.** Seria o pior erro
  possível: a rotina "funcionaria" lendo cópia velha, e a defasagem voltaria a ser
  invisível. Há um teste só para isso.
- **Confere o thumbprint** calculado do próprio `.pfx` contra o esperado, antes de
  tocar a rede. Um certificado trocado falha ali, com o motivo — não lá na frente
  com um 401 mudo.

**Bloqueado em 24/08:** a conta `fillipe.figueiro@gridco.com.br` recebe
*Access denied* no conteúdo do site (o Graph devolve `/drives` vazio). Falta o TI
conceder acesso às **pessoas** — a concessão feita foi só para o aplicativo.

**Limite técnico para depois:** o Graph aceita upload simples até 4 MB. A
Gerencial (813 KB) e o Histórico passam; o `BD_Relatório Semanal.xlsx` (6,7 MB)
exige `createUploadSession`.

---

## 6g. Decisão de 24/08: os repositórios seguem públicos

O `banco_dados.json` (4,4 MB, todos os clientes) continua baixável por qualquer um
via `raw.githubusercontent`. Não é mais **navegável** — o Pages foi desligado e o
painel só abre com login Microsoft — mas quem souber a URL baixa o arquivo.

**A contrapartida medida:** repositório público tem minutos de Actions ilimitados.
Os três robôs consomem **652 min/dia** (semanal 260 + gestao-pcm 311 + azure-swa
81), o que dá ~19.500 min/mês contra uma cota de 2.000 em repositório privado.
O excedente custaria **~US$ 140/mês**.

Decisão do Fillipe: seguir público por enquanto. O caminho que tornaria o
privado viável é tirar o dado do git — que é justamente para onde o §6f aponta.

⚠ O raw serve com `Content-Type: text/plain` e `X-Content-Type-Options: nosniff`,
então o painel **não roda** de lá: os arquivos são legíveis, não executáveis. Foi
o que tornou o desligamento do Pages uma redução real, e não cosmética.

---

## 7. Inventário de acesso

| | |
|---|---|
| Repositório | `fillipefigueiro-source/gridco-pcm-data`, **público**. Dono: Fillipe |
| Azure | `swa-gridco-painel`, RG `rg-gridco-campo`, assinatura Grid, **plano Standard** (US$ 9/mês desde 20/08) |
| Entra ID | registro `Painel PCM - Grid Co.`, appId `2b16d732-3596-46f9-86bf-299b2964542e`, segredo válido até 2028 |
| Blob | `stgridcocampomw`, container `acessos`, SAS até 2028 |
| Fracttal | código de pessoa **02** |
| Papéis | `admin` (tenant Grid, automático), `equipe` (definido, hoje ninguém recebe), `cli-*` por cadastro |

### O que hoje só uma pessoa consegue fazer

- **Regenerar o `mpas.json`** — depende da senha de cifra
- **Atualizar a Gestão MPAS** — depende da Gerencial no OneDrive e de alguém clicar
- **Editar `.github/workflows/`** — exige escopo `workflow`
- **Cadastrar app settings no Azure**

---

## 8. Como manter este arquivo

Ele existe porque coisas caras de descobrir estavam só em conversa: a regra de
ouro, o contrato de escrita do Fracttal, e o fato de que **sombra não faz
barulho**.

Quando descobrir a próxima, **escreva aqui — não no e-mail**. E se for uma falha
que não avisa quando acontece, ela pertence à §6.
