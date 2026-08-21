# Estado do painel PCM — o que não está óbvio no código

Escrito em 21/08/2026 a pedido do Fillipe, para consolidar no repositório o que
estava espalhado entre e-mails, a máquina do PCM e a cabeça de quem construiu.

**O que este arquivo NÃO contém:** nenhuma credencial, senha ou token. Eles
continuam onde devem estar (GitHub Secrets, app settings do Azure, `.env` local)
e são passados por canal direto, nunca por arquivo ou e-mail. A seção
"Credenciais" abaixo diz apenas **onde cada uma vive** e o que quebra sem ela.

---

## 1. O que roda onde

### Na nuvem (GitHub Actions), sozinho

| Workflow | O que faz | Cadência REAL |
|---|---|---|
| `semanal.yml` | `atualizacao_semanal.py` + `gerar_pcm_json.py` + `gerar_etiquetas_json.py` → publica `banco_dados.json` e `etiquetas.json` | cron diz `*/15`, mas o GitHub atrasa: medido em 21/08 deu **29, 68 e 48 min** entre execuções |
| `gestao-pcm.yml` | `gerar_gestao_pcm_json.py` → `gestao_pcm.json` | idem |
| `azure-swa.yml` | deploy do painel no Azure SWA | por push (ver problema em §3) |

> **Não confie no `*/15`.** Quem precisar de atualização imediata: Actions →
> workflow → *Run workflow* (`workflow_dispatch`), que não sofre o atraso.

### Na máquina do PCM, manual (PCM_Painel)

Nada disso está agendado — **se ninguém abrir o programa, não acontece**:

| Botão | Script | Quando |
|---|---|---|
| Gerar Programação Semanal | `programacao_v7.py` | sexta, gera a semana seguinte |
| Enviar semana pra nuvem | `publicar_semana_github.py` | logo depois de gerar |
| Programação Semanal Clientes | `gerar_relatorio_cliente.py` | sexta, depois do time aprovar |
| Atualizar Gestão MPAS | `atualizar_mpas.py` | quando a Gerencial muda |
| Rodar Atualização Diária | `atualizacao_semanal.py` | durante a semana |

**A Gestão MPAS é o caso mais frágil:** a fonte é o
`Gerencial - PCM_2026_R00.xlsx` no OneDrive, que o robô da nuvem **não enxerga**.
Esse JSON só atualiza por ação manual.

### Onde o código realmente mora

Os scripts vivem **neste repositório**. A pasta do OneDrive tem **shims** que
delegam (`atualizacao_semanal.py`, `gerar_pcm_json.py`, `programacao_v7.py`…).
Editar o shim não tem efeito. Já aconteceu de sobrescrever um shim com o arquivo
real por engano — se um deles passar de ~1 KB, é sinal disso.

---

## 2. Credenciais — onde vivem e o que quebra sem elas

| Segredo | Onde vive | Quebra o quê se sumir |
|---|---|---|
| `FRACTTAL_CLIENT_ID` / `_SECRET` | GitHub Secrets **e** `.env` local | os dois robôs e todo script que fala com a API |
| idem, nas **app settings do SWA** | **AINDA NÃO CADASTRADO** | `/api/motivos` — o motivo escolhido no painel não grava na OS |
| `PCM_MPAS_SENHA` (cifra do `mpas.json`) | só na cabeça do PCM | ninguém regenera o `mpas.json`; a aba Gestão MPAS não abre |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | GitHub Secrets | o deploy do Azure |
| `AZURE_CLIENT_ID` / `_SECRET` | app settings do SWA | o login Microsoft inteiro |
| `LISTA_PRIORIDADES_B64`, `CONFIABILIDADE_B64` | GitHub Secrets | os robôs (é o base64 das planilhas) |

**As planilhas de origem existem no OneDrive** (conferido em 21/08):
`Lista_Prioridades_GridCo.xlsx` (18/06) e `Planilha Confiabilidade R00.xlsx`
(27/05). Ou seja, os dois Secrets são reconstituíveis — não são ponto único.

**A senha do `mpas.json` é o único ponto único de falha real da lista.**

---

## 3. O que está quebrado ou pendente, hoje

### Bloqueia uso

- **As 3 app settings do Fracttal no SWA** — sem elas o bloco de motivos das
  16h não grava na OS. É o item que trava o uso pelos supervisores.
- **`mpas.json` publicado EM CLARO** no repositório público. O gerador foi
  corrigido para falhar fechado, mas **falta republicar** com a senha. O arquivo
  tem observações em texto livre, incluindo nota de pessoal.
- **Passo 4 (desligar o Pages)** — o `github.io` serve `banco_dados.json` sem
  autenticação nenhuma. Enquanto estiver de pé, a proteção do Azure convive com
  uma porta aberta ao lado.

### Achados do `rolesSource` ainda não corrigidos

O `rolesSource` foi publicado em 20/08. Dois achados da revisão continuam de pé:

1. **Não há lista de papéis válidos.** `ACESSO_CLI_THOPPEN` (typo) devolve
   `cli-thoppen`; o Azure aceita e o painel não conhece — a pessoa fica
   cadastrada e vê "conta sem papel".
2. **`claim()` casa qualquer tipo terminado em `/tenantid`.** Reproduzido: conta
   externa com `urn:x/tenantid` antes do claim canônico vira `equipe`.

Um terceiro, menor: e-mail em dois `ACESSO_CLI_*` resolve pela ordem de
`process.env`, que não é contratual.

### Deploy do Azure

O gatilho por push **não funciona com os commits do robô** — eles usam o
`GITHUB_TOKEN`, e o GitHub não dispara workflow a partir dele (regra anti-loop).
O Fillipe mexeu nisso em 20/08 (`cf7d9818`), e houve deploys por push do robô em
21/08 às 12:30 e 12:45 — mas o último foi **12:50** e parou de novo. **Ainda não
está resolvido de forma confiável.** A correção proposta está em
`_azure/azure-swa.yml`: trocar o gatilho por `workflow_run` (dispara depois que
cada robô termina).

Existem **dois** `azure-swa.yml`: o que roda (`.github/workflows/`) e o molde
(`_azure/`). O molde tem cabeçalho avisando que não roda.

### Conhecido e deliberadamente não tratado

- **1.059 tarefas abertas dentro de OS com status `Finalizados`.** É problema de
  cadastro, não de programação. O filtro de topo do motor as exclui de propósito.
  **Decisão do PCM: fora de escopo.**

---

## 4. Decisões que o código aplica e que não se deduzem lendo

### A regra de ouro

**Status da OS ≠ Estado da Tarefa.** Concluído é `Estado da Tarefa ==
'Finalizada'`, nunca o status da OS. Existe OS `Finalizados` com tarefa aberta e
o contrário. Todo cálculo de conclusão usa o estado da TAREFA.

### Fila de reprogramação entre semanas (21/08)

Tarefa vencida volta para a semana seguinte, com regra por sigla:

- **MPM, MPW, MPQ, MPT** → só do **mês corrente** (mensal de mês passado não se
  executa mais)
- **MPS, MPA** → de **qualquer mês** (semestral/anual atrasada continua valendo)
- **Corretiva e Inspeção** → sempre (tier 0 e 1 da régua da rolagem)
- **Handover e Administrativa** → nunca (não é manutenção de campo)
- **Religamento** → já excluído pelo motor

Regra que originou tudo: **MPM do mês corrente NUNCA pode ficar invisível** — ou
está na semana, ou aparece em "Não couberam na semana". Nunca em lugar nenhum.
Ligada por `PCM_FILA` (padrão `ativo`).

### O pin manda (21/08)

Observação com dia é **ordem, não sugestão**. Se o dia pedido está cheio, o motor
força a entrada marcando `[EXCEDE HH]`, em vez de mandar para pendentes.

Ao implementar isso descobriu-se que **o `force` do `alloc_diurno` nunca forçou**:
pulava as guardas de entrada e era barrado nas de saída (`effective_min` truncava
para a capacidade restante, zero num dia cheio). Consequência: a corretiva
"forçada `[EXCEDE HH]`" só entrava quando ainda havia capacidade — ou seja,
quando não precisava forçar. Corrigido; **isso mudou o comportamento das
corretivas em dias lotados também**.

### Rolagem do dia

`ROLAGEM_MODO_DEFAULT = "ativo"` desde 21/08. Ficou em **sombra desde que foi
escrita** — registrava o que rolaria e nada se movia, e ninguém percebeu, porque
sombra não faz barulho. Trata o DIA (segunda não feita vai para terça); o que
atravessa a SEMANA é a fila acima.

### Escrita no Fracttal (`/api/motivos`)

`PUT /work_orders/{WO_FOLIO}` com `{"note": <texto completo>, "account_code": "02"}`.
Quatro armadilhas: o path é o **folio**, não o `id_work_order`; `account_code` é
código de **pessoa** (02 = Fabricio, e a alteração fica atribuída a ele); valor
vazio é recusado (não dá para limpar pela API); só grava em OS **em processo ou
em revisão**.

A escrita **substitui o campo inteiro** — não existe append. Por isso é ler →
concatenar → gravar, relendo imediatamente antes do PUT para não atropelar quem
edita pela tela.

**Duas linhas do mesmo dia para a mesma tarefa são permitidas de propósito** —
decisão do PCM: a tarefa pode não ter sido feita por dois motivos.

### Decisão 28 reescrita (19/08)

Deixou de ser *"privar o repositório"* e passou a ser **"tirar o dado do
repositório"** (opção 3). Motivo: privar não resolve a cota do Actions (≈47.700
min/mês contra 2.000), e runner self-hosted em repo público é inseguro. Com a
opção 3, a cota deixa de importar e a exposição fecha. O `AUXILIAR - FABRICIO.xlsx`
entra na mesma mudança.

### Filtro por papel é lista de PERMISSÃO

Em `api/dados/index.js`, só os campos explicitamente copiados saem para o
cliente. **Nunca trocar por um spread do objeto** — seria o caminho para vazar um
bloco novo sem ninguém perceber. Mesmo princípio na config do SWA:
`{"route":"/*.json","allowedRoles":["admin","equipe"]}` faz arquivo novo **nascer
fechado**.

---

## 5. Inventário de acesso

| | |
|---|---|
| Repositório | `fillipefigueiro-source/gridco-pcm-data`, **público**. O dono é o Fillipe; o PCM tem token com `contents:write` (empurra código) mas **não** `actions:write` — não consegue disparar workflow pela API |
| Azure | recurso `swa-gridco-painel`, RG `rg-gridco-campo`, assinatura Grid, plano **Standard** (US$ 9/mês desde 20/08). Criado e administrado pelo Fillipe |
| Fracttal | conta do PCM, código de pessoa **02** |
| Papéis do painel | `admin` (PCM), `equipe` (tenant Grid, automático via rolesSource), `cli-*` por cadastro |

### O que hoje só uma pessoa consegue fazer

- **Regenerar o `mpas.json`** — depende da senha de cifra, que só o PCM tem.
- **Atualizar a Gestão MPAS** — depende da Gerencial no OneDrive, invisível para
  a nuvem, e de alguém clicar no botão.
- **Disparar workflow / editar `.github/workflows/`** — só o Fillipe (o token do
  PCM não tem escopo).
- **Cadastrar app settings no Azure** — só o Fillipe.

---

## 6. Como manter este arquivo

Ele existe porque três coisas caras de descobrir estavam só em conversa: a regra
de ouro, o contrato de escrita do Fracttal e o fato de que sombra não faz
barulho. Quando descobrir a próxima, escreva aqui — não no e-mail.
