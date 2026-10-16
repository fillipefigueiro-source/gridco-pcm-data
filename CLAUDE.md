# CLAUDE.md — contrato de trabalho neste repositório

Plataforma PCM da Grid Co.: o painel `pcm.gridco.com.br`, quatro automações no GitHub
Actions, nove funções de API no Azure e a geração da programação semanal de manutenção.
Está **em produção** e o time de O&M usa todo dia. A origem do dado é o Fracttal (CMMS);
nada é digitado à mão.

Para profundidade: `HANDOVER.md` (o mapa) e `ESTADO.md` (o histórico de tudo que custou
caro descobrir — a §6 é a parte que mais evita estrago).

---

## Nunca faça

- **Não regenere o `novo.html`.** Ele é fonte, não é gerado. Existiu um `construir_novo.py`;
  está aposentado. Regenerar apaga trabalho sem avisar.
  Detector de integridade: o arquivo tem que conter `_semanaEscolhida`, `trocarSemana` e
  `_semPapel(_s.quem)`.
- **Não altere `programacao_v*.py` nem `atualizacao_semanal.py`** sem revisão explícita de
  quem pediu. São o motor da programação; mudança errada ali chega ao campo.
- **Não sobrescreva o `Historico_Programacoes.xlsx`.** Só o `programacao_v7.py` escreve lá.
- **Não versione dado de pessoa.** O repositório é **público**, por decisão de custo
  consciente (Actions ilimitado em repo público). Nada de CPF, telefone, endereço ou e-mail
  em arquivo versionado. Antes de subir script novo vindo de uma máquina, audite o conteúdo.
- **Não rode `atualizar_mpas.py` sem `--so-gerar`** enquanto o publicador do `mpas.json` não
  for identificado — ver o aviso na §2 do `HANDOVER.md`.

## Sempre faça

- **Mudança de interface passa por mockup e aprovação antes de subir.** Monta-se, mostra-se,
  só então publica.
- **Toda falha silenciosa descoberta vai para o `ESTADO.md`**, não para a conversa. O arquivo
  existe porque coisas caras de descobrir estavam só na cabeça de alguém.
- **`git fetch` antes de medir idade de arquivo.** Três robôs commitam a cada 15 min; um
  checkout atrasado faz `git log` medir o passado e mentir com confiança.
- **Verifique antes de publicar.** O repositório é estático: sirva a pasta e abra o painel.

---

## Armadilhas técnicas

**Finais de linha misturados no `novo.html`.** Patch por texto precisa tentar `\n` **e**
`\r\n`, senão a âncora não casa. Padrão pronto:

```python
def troca(a, b):
    for na, nb in ((a, b), (a.replace("\n", "\r\n"), b.replace("\n", "\r\n"))):
        if s.count(na) == 1:
            return s.replace(na, nb)
    raise AssertionError("âncora não única/ausente: " + a[:80])
```

**Seletores globais no painel.** O `ligar()` do `novo.html` varre o documento inteiro
procurando `.ftxt`, `.pv-cli`, `[data-f]`, `[data-gf]`, `[data-gt]`, `[data-i]`, `th[data-c]`
e `th[data-pc]`. Reusar qualquer um desses num módulo novo liga um comportamento que você não
pediu. Use prefixo próprio — já em uso: `rp-`, `cf-`, `gr-`, `gp-`, `pv-` no `novo.html`
e `rx-` no `js/relatorios.js`.

**Os arquivos da pasta do OneDrive são shims.** Delegam para este repositório; editar o shim
não tem efeito. Se algum passar de ~1,5 KB, alguém o sobrescreveu com o arquivo real — e as
duas cópias divergem em silêncio. São dezesseis.

**Caminho por `__file__` é contrato.** Vários scripts resolvem entrada e saída a partir da
própria localização, com `PCM_PROG_DIR` tendo prioridade. Mover um script de pasta muda onde
ele grava, **sem erro nenhum**. Verifique antes de mover.

**Robô contra robô.** Os workflows commitam no mesmo repositório em ciclos de 15 minutos.
Todo passo de publicação precisa do laço de rebase com `--theirs` nos arquivos gerados.
Copie o padrão de um workflow existente; não invente outro.

**O `GITHUB_TOKEN` padrão do Actions não dispara outro workflow.** Por isso existe o
encadeamento explícito por `workflow_run` no `azure-swa.yml`.

**Paginação do Fracttal: `page_size=100`.** Acima disso a API trunca em silêncio e devolve
sucesso.

---

## Regras da semana

**A tarefa programada na sexta não muda de dia até o fechamento da semana** (Levi, 16/10/2026: "se foi para terça
fica na terça"). O campo pode executá-la depois, mas ela continua no dia dela, para o relatório diário medir o que foi
feito no dia programado.
- O STEP A4 (rolagem, `aplicar_rolagem`) está **desligado** (`ROLAGEM_MODO_DEFAULT = "desligado"`;
  `PCM_ROLAGEM=ativo` religa). Ele levava para hoje a corretiva e a prioritária não finalizadas: na rodada de 16/10
  15:00 foram 125 tarefas roladas, 105 forçadas além do HH e 620 levadas para a `_Pendentes`. Era isso que "mascara a
  execução deixando um backlog arrastado".
- A cascata da OS nova (STEP A2) e do pin do PCM (STEP A3), `deslocar_conflitantes`, só anda no relógio **do mesmo dia**.
  Sem lugar no expediente, a tarefa fica no dia, depois da última, marcada `[EXCEDE HH]`. Nunca vai para outro dia nem
  para a `_Pendentes`. O pin do PCM ainda muda o dia da OS citada na observação.

**Carga máxima do dia: 70%** (`CARGA_MAX_DIA` no `programacao_v7.py`, da W44 em diante): 6,15 h por equipe e dia das
8,8 h líquidas (era 80%, 7 h). A folga é do campo: quem acabar antes faz as tarefas dos dias seguintes da usina em que
estiver, e a OS nova da semana cabe sem empurrar a de sexta. A janela da noite continua em 80% (`NIGHT_CAPACITY_MIN`).
O Nexus tem a cópia idêntica do motor (`nexus/pcm/motor`) e a conferência dele usa a mesma carga
(`nexus/pcm/comparar.py`).

---

## Fontes de verdade

| Dado | Vem de |
|---|---|
| Tempo médio de corretiva | `Planilha Confiabilidade R00.xlsx`, aba "Resumo por Categoria", coluna "Média (h)" |
| Ordens e tarefas | Fracttal, via `fonte_bd_api.py` |
| Sigla da preventiva | do texto da tarefa — **MPA tem duas grafias**: a sigla e "Manutenção Preventiva Anual GRID CO." Ler só a sigla captura menos de um terço |
| Duração aprendida | `duracoes_aprendidas.json` — medida, mas **o motor não consome**. É proposital: ver `ESTADO.md`, "Primeira medição real" |
| O que fica fora da programação | `Fora_da_programacao.json`, **gravado pelo Nexus** (16/10/2026): a tarefa com motivo que tira da programação (Aguardando Material, Aguardando Cliente...) e os nomes do backoffice. Lido por `fora_da_programacao.py` no `programacao_v7` (não programa) e no `atualizacao_semanal` (A2 não inclui como OS nova, A3b apaga da semana em curso a tarefa com motivo; a OS do backoffice já na semana fica). Não edite à mão: a próxima marca no Nexus regrava. Sem o arquivo, nada fica de fora |

---

## Como rodar

```bash
pip install -r requirements.txt

python aprender_duracoes.py --dry-run        # confere o acesso ao Fracttal, sem escrever
python -m http.server 8765 --directory .     # serve o painel; abra /novo.html
python sync_repo.py "tipo: resumo"           # commit + push que sobrevive ao robô
```

No painel local, só o `/.auth/me` dá 404 — é esperado, a autenticação é do Azure.

A pasta de trabalho do PCM (planilhas de entrada e saída) é encontrada por `PCM_PROG_DIR`,
ou por autodetecção do OneDrive. Defina a variável se a autodetecção falhar.

---

## Convenções

- **Português** em código, comentário, commit e documento.
- **Commits** no formato `tipo: resumo` — `feat`, `fix`, `chore`, `docs`.
- **Comentário explica porquê, não o quê.** O código já diz o quê. O que se perde é a razão,
  e é ela que impede a próxima pessoa de "simplificar" algo que existe por um motivo.
- **O cliente nunca vê o processo de reprogramação** — só o resultado. Vale para painel,
  relatório e e-mail.
