# Descontinuado — **não execute nada daqui**

Estes scripts vieram para o git em 22/09/2026, na transição, porque até então existiam
só na máquina de uma pessoa. Estão aqui pelo **histórico**, não para uso.

Foram separados da raiz de propósito: três deles ainda funcionam, e rodar qualquer um
faria o autor brigar com um robô que já publica o mesmo arquivo a cada 15 minutos.

## Substituídos por um robô

Publicavam à mão um arquivo que hoje um workflow mantém sozinho. **Rodar isto hoje
sobrescreve o que o robô publicou**, e o robô sobrescreve de volta no próximo ciclo.

| Script | Quem faz isso hoje |
|---|---|
| `publicar_pcm_github.py` | `semanal.yml` → `banco_dados.json` |
| `publicar_etiquetas_github.py` | `semanal.yml` → `etiquetas.json` |
| `publicar_gestao_pcm_github.py` | `gestao-pcm.yml` → `gestao_pcm.json` |

## Cópia antiga com sufixo de máquina

`cadastro_usina_fracttal-FILLIPE-FIGUEIRO.py` — cópia de 04/09/2026. O
`cadastro_usina_fracttal.py` na raiz, de 14/09, é superconjunto: 41 linhas a mais,
incluindo intervalo de índice no campo de quantidade (tipo `6-15`).

Guardado só como prova do problema que o `ESTADO.md` já descrevia em "Dois arquivos com
o mesmo nome": **cópia com sufixo de máquina diverge da original em silêncio.** Se você
se pegar criando um `algo-SEUNOME.py`, é sinal de que falta resolver outra coisa.

## Sondas e migrações de uma vez só

Já cumpriram o que tinham que cumprir. O valor que sobrou está na conclusão, não no código.

| Script | O que era | O que ficou |
|---|---|---|
| `debug_paginacao.py` | sondar a paginação do Fracttal | a regra `page_size=100`, acima disso trunca em silêncio |
| `_amostra_etiquetas.py` | entender o formato das etiquetas | virou o `gerar_etiquetas_json.py` |
| `_amostra_tipo_tarefa.py` | entender `tasks_types` | a classificação por sigla no painel |
| `_teste_relatorio_estilo.py` | protótipo de estilo do relatório | virou o `relatorio_clientes.py` |
| `_dados_athon_junho.py` | levantamento de um mês | entregue em junho/2026 |
| `_dados_axis_mpas.py` | levantamento de um cliente | entregue em julho/2026 |
| `dedup_bd_relatorio.py` | remover duplicatas do BD | migração executada |
| `limpar_duplicatas_programacao.py` | idem, na programação | migração executada |
| `migrar_abas_clusters.py` | reorganizar abas por cluster | migração executada |

> As sondas trazem um caminho fixo da máquina de quem as rodou e uma data fixa no código.
> Não rodam em outra máquina sem edição, e é melhor assim.
