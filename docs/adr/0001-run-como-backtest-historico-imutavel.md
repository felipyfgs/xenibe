# ADR 0001: Run como backtest historico imutavel

Status: Aceita
Data: 2026-06-30

## Contexto

O codigo expunha `forge run backtest` e `forge run simulate`, mas ambos chamavam o mesmo fluxo de backtest, usavam o mesmo motor M1 e diferiam basicamente por `mode` e prefixo de `runId` (`bt-` ou `sim-`). Isso fazia `simulate` parecer uma capacidade de dominio ja definida, sem comportamento proprio.

## Decisao

No estado atual do Xenibe, `run` significa uma avaliacao historica imutavel de uma configuracao de experimento sobre candles historicos. O modo concreto implementado e `backtest`.

`mode` descreve o mecanismo de execucao historica. O campo `subject` deve descrever o que foi avaliado, por exemplo `candidate-search` ou `promoted-robot`.

`simulate` nao deve ser tratado como modo real enquanto nao tiver contrato observavel proprio. Um futuro modo de simulacao precisa definir antes suas diferencas de dominio, entradas, garantias e artefatos.

## Consequencias

- `bt-*` e o unico identificador canonico de runs reais no dominio atual.
- `mode=backtest` pode cobrir mais de um `subject`, desde que todos sejam avaliacoes historicas imutaveis.
- `sim-*` nao deve validar como run canonico sem uma nova decisao de dominio.
- A CLI, os schemas e a documentacao devem evitar sugerir que `simulate` existe como comportamento equivalente a backtest.
- Uma futura simulacao operacional precisa de nova decisao antes de ser implementada.
