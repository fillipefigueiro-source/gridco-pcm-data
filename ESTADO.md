# Estado do painel PCM — o que não está óbvio no código

**Última atualização: 21/08/2026.** Base escrita pelo Fabrício; ampliada com o que
foi descoberto e alterado em 19–21/08.

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

### Onde o código realmente mora

Os scripts vivem no repositório. A pasta do OneDrive tem **shims** que delegam.
Editar o shim não tem efeito. **Se um deles passar de ~1 KB, alguém sobrescreveu
o shim com o arquivo real.** Conferido em 21/08: todos entre 921 e 942 bytes.

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

**Nenhum item aberto** desde 21/08 17:15. Os três que bloqueavam foram fechados:
app settings do Fracttal, gatilho do deploy e acesso da equipe.

### Aberto, sem bloquear

**1. Colisão de push no `gestao_pcm.json`** — *achado em 21/08, sem correção.*

O robô `gestao-pcm.yml` falha no step 6 ("Publicar só se os dados mudaram"),
esgotando as **5 tentativas** com `pull --rebase`. Falhou às 16:28 e 17:02 de
21/08. O step 5 (gerar via API) passa — o problema é só o push.

Causa: **a nuvem e a máquina local geram o mesmo arquivo, da mesma API, e
empurram para o mesmo branch.** Os commits locais (autor `fillipefigueiro-source`)
às 16:30, 16:45 e 17:02 batem exatamente com as falhas.

Por que é perigoso: enquanto a máquina local publicar, o dado chega e **a falha do
robô não tem consequência visível**. Se a máquina parar, a Gestão PCM congela sem
erro em lugar nenhum.

Correção: **um dos dois tem que parar.** O robô da nuvem deve ser o único
publicador — ele já funciona. Antes de desligar a sincronização local, é preciso
saber exatamente o que ela publica que a nuvem não gera.

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

**Resolver o caminho da senha sob o login Microsoft antes de cifrar** — o cadeado
precisa pedir a senha na hora, em vez de depender de uma tela que não existe mais.

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
