# HANDOVER — onboarding do desenvolvedor

Escrito em 22/09/2026 para a passagem do projeto ao **Levi**.

Este arquivo é o caminho de entrada. Ele não repete o que já está escrito em outro lugar —
aponta para lá e diz **em que ordem ler**.

| Arquivo | O que é | Quando ler |
|---|---|---|
| `HANDOVER.md` | este arquivo, o mapa | primeiro |
| `CLAUDE.md` | as regras que não se violam | antes do primeiro commit |
| `ESTADO.md` | 1.196 linhas de tudo que custou caro descobrir | §6 no primeiro dia, o resto ao longo da semana |

> **A leitura mais importante do repositório é a `§6` do `ESTADO.md`.** São falhas que
> **não avisam quando acontecem**. Todas já ocorreram em produção. Ler depois de quebrar
> alguma coisa é caro; ler antes leva quarenta minutos.

---

## 1. O que é a plataforma

Sustenta a programação de manutenção da Grid Co., de ponta a ponta:

- o **painel** `pcm.gridco.com.br` — página única, login Microsoft, módulos de Semana,
  Gestão PCM, Confiabilidade, Gerencial e Relatórios;
- **três robôs** no GitHub Actions que mantêm o dado vivo sem ninguém tocar;
- **dez funções de API** no Azure (pasta `api/`), que fazem o que o navegador não pode:
  falar com o Fracttal com credencial, gravar ticket, ler papéis;
- a **geração da programação semanal**, hoje ainda na máquina do responsável (ver §6).

A origem de tudo é o **Fracttal**, o CMMS da Grid Co. Nada é digitado à mão no painel.

---

## 2. O que roda onde — o mapa que evita a maioria dos enganos

### Roda sozinho, na nuvem (GitHub Actions)

| Workflow | Quando | O que faz |
|---|---|---|
| `semanal.yml` | a cada 15 min | `atualizacao_semanal.py` → `banco_dados.json`, `etiquetas.json` |
| `gestao-pcm.yml` | a cada 15 min | `gerar_gestao_pcm_json.py`, `gerar_engenharia_json.py`, `relatorio_diario.py` → `gestao_pcm.json`, `engenharia.json`, `gerencial.json`, `relatorios/` |
| `duracoes.yml` | sexta, 05:00 BRT | `aprender_duracoes.py` → `duracoes_aprendidas.json` |
| `azure-swa.yml` | a cada push | publica o site no Azure Static Web Apps |

### Roda na máquina de uma pessoa — **é o que esta transição tem que acabar**

| O quê | Produz | Situação em 22/09 |
|---|---|---|
| `programacao_v7.py` | `Programação Semana XX.xlsx` | sexta-feira, manual. **Fase 3 leva para a nuvem** |
| `gerar_mpas_json.py` | `mpas.json` | script **fora do git** + senha de cifra |
| `gerar_confiabilidade_json.py` | `confiabilidade.json` | script **fora do git** — dado parado desde 31/07 |
| `gerar_supervisores_json.py` | `supervisores.json` | script **fora do git** — parado desde 31/07 |
| `exportar_operacoes.py` | `operacoes.json` | manual |

> **Se um dado do painel parece velho, comece por esta tabela.** Seis fontes são de robô e
> estão sempre em dia; as quatro daqui dependem de alguém lembrar de rodar. Duas estão
> paradas há 52 dias e ninguém percebeu — porque **sombra não faz barulho**.

### Os scripts que vieram para o git na transição

Até 22/09/2026 havia **33 scripts que só existiam numa máquina**. Todos foram versionados.
Vinte ficaram **na raiz**, porque resolvem caminho por `__file__` e mover mudaria onde
gravam. Treze foram para `ferramentas/descontinuado/`, que tem um README explicando cada um
— **não rode nada de lá**: três deles ainda funcionam e brigariam com os robôs.

Dos que ficaram na raiz, os que importam no dia a dia:

| Script | Para quê |
|---|---|
| `gerar_confiabilidade_json.py` | regenera o `confiabilidade.json` do módulo Confiabilidade |
| `gerar_supervisores_json.py` | regenera o `supervisores.json` |
| `gerar_mpas_json.py` / `atualizar_mpas.py` | regeneram a aba MPAS — **precisam da senha de cifra** |
| `cadastro_usina_fracttal.py` | cadastra usina nova no Fracttal (a maior ferramenta, 50 KB) |
| `relatorio_clientes.py` | relatório do cliente; lê contatos de arquivo fora do git |
| `lancamento_desembolsos.py` + `desembolsos_core.py` | módulo de desembolsos |
| `gui_pcm.py` / `gui_relatorios.py` | interfaces locais do PCM |
| `publicar_*_github.py` | publicam à mão o que nenhum robô publica |

### Não é nosso

O aplicativo de campo é servido por **`gridco-campo-mw`**, uma Function App em Python na mesma
assinatura Azure (RG `rg-gridco-campo`). **Ela lê o Fracttal direto**, não os nossos arquivos.
Quem mantém é outro time. Se a demanda for sobre o app do técnico, o endereço é lá.

---

## 3. Primeiro dia — ambiente

```bash
git clone https://github.com/<organização>/gridco-pcm-data.git
cd gridco-pcm-data
pip install -r requirements.txt
```

Depois, **as variáveis de ambiente**. Nenhuma delas vai para o git:

| Variável | Para quê | Onde conseguir |
|---|---|---|
| `FRACTTAL_CLIENT_ID` / `FRACTTAL_CLIENT_SECRET` | ler o CMMS | Secrets do repositório |
| `GITHUB_TOKEN` | `sync_repo.py` publicar | token próprio seu, escopo `repo` + `workflow` |
| `PCM_PROG_DIR` | achar a pasta do PCM no OneDrive | sua própria sincronização |

Para conferir que ficou de pé, sem escrever nada:

```bash
python aprender_duracoes.py --dry-run
```

Se ele listar durações por categoria, o acesso ao Fracttal está bom.

---

## 4. As cinco armadilhas que mais custam

Estão detalhadas no `ESTADO.md`. O resumo existe aqui porque são as que pegam gente nova.

**1. Não regenere o `novo.html`.** Ele é **fonte**, não é gerado. Existiu um
`construir_novo.py` que o montava; está aposentado. Regenerar apaga trabalho sem avisar.
Detector: o arquivo tem que conter `_semanaEscolhida`, `trocarSemana` e `_semPapel(_s.quem)`.

**2. O `novo.html` tem finais de linha misturados.** Patch por texto precisa tentar `\n` **e**
`\r\n`, senão a âncora não casa. Há exemplo pronto nos scripts de patch.

**3. Os arquivos na pasta do OneDrive são _shims_.** Eles delegam para o repositório. Editar o
shim não tem efeito nenhum. **Se algum passar de ~1,5 KB, alguém sobrescreveu o shim com o
arquivo real** — e a partir dali as duas cópias divergem em silêncio.

**4. O `GITHUB_TOKEN` padrão do Actions não dispara outro workflow.** Se um robô commita e você
espera que isso acione o deploy, não aciona. É por isso que existe o encadeamento explícito por
`workflow_run` no `azure-swa.yml`.

**5. Robô contra robô.** Três workflows commitam no mesmo repositório em ciclos de 15 minutos.
Todo passo de publicação precisa do laço de `rebase` com `--theirs` nos arquivos gerados. Copie
o padrão de um workflow existente; não invente outro.

---

## 5. Publicar uma mudança no painel

1. Edite `novo.html` (ou `js/`, `css/`) direto.
2. **Mudança de interface vai para aprovação antes de subir.** É regra de quem tocou o projeto
   até aqui, e vale: monta-se um mockup, mostra-se, só então sobe.
3. Verifique localmente antes de publicar — o repositório inteiro é estático:
   ```bash
   python -m http.server 8765 --directory .
   ```
   Abra `http://localhost:8765/novo.html`. Só o `/.auth/me` dá 404, e é esperado.
4. `git push`. O `azure-swa.yml` publica em poucos minutos.
5. No navegador, `Ctrl+F5` — o painel é agressivo com cache.

Se precisar de um commit + push que sobreviva ao robô commitando no meio:

```bash
python sync_repo.py "mensagem do commit"
```

---

## 6. O que está pendente

| Pendência | Onde está |
|---|---|
| Levar o `programacao_v7.py` para a nuvem | fase 3 do plano de transição |
| Versionar os 33 scripts que só existem numa máquina | fase 1 |
| Regenerar `confiabilidade.json` e `supervisores.json` | fase 2 |
| Cadastrar os Secrets de SMTP | os relatórios já geram PDF; o e-mail está dormente |
| Especificação "OS Preventivas e Handover" v2 | para o time do `gridco-campo-mw` |
| Duração aprendida ligada (`PCM_DURACAO_APRENDIDA`) | **não ligar** — ver abaixo |

> **Sobre a duração aprendida:** o `duracoes.yml` mede a duração real toda sexta, mas o motor
> **não a consome**. É proposital. A medição de 18/09 mostrou que o número reflete o hábito de
> apontamento da equipe, não o trabalho: dentro de uma mesma usina todas as categorias colapsam
> no mesmo valor, e em 7 de 24 usinas a preventiva anual mede **menos** que a mensal. Ligar hoje
> faria o programador reservar quatro horas para uma mensal em Matões. Ver `ESTADO.md`,
> "Primeira medição real".

---

## 7. Convenções

- **Português** em código, commit e documento. É a língua do time que usa isto.
- **Commits** no formato `tipo: resumo` (`feat`, `fix`, `chore`, `docs`).
- **Toda falha silenciosa descoberta vai para o `ESTADO.md`**, não para o e-mail. O arquivo
  existe porque coisas caras de descobrir estavam só em conversa.
- **O repositório é público**, por decisão de custo consciente (Actions ilimitado; privado
  custaria ~US$ 140/mês). Consequência prática e inegociável: **nada de CPF, telefone, endereço
  ou e-mail de pessoa entra em arquivo versionado.** Confira o `.gitignore` antes de criar
  arquivo novo com dado de cliente.
- **O cliente nunca vê o processo de reprogramação** — só o resultado. Vale para painel,
  relatório e e-mail.
