# ADR 0001: Run como backtest historico imutavel

Status: Aceita
Data: 2026-06-30

## Contexto

O codigo expunha comandos de run em um namespace publico interno. A superficie compacta atual concentra a execucao em `forge backtest <experiment>` e permite solicitar simulacao com `--mode simulate`, preservando um unico caminho operacional de pesquisa historica.

## Decisao

No estado atual do Xenibe, `run` significa uma avaliacao historica imutavel de uma configuracao de experimento sobre candles historicos. Os modos publicos aceitos sao `backtest` e `simulate`.

`mode` descreve o mecanismo de execucao historica. O campo `subject` deve descrever o que foi avaliado, por exemplo `candidate-search` ou `promoted-robot`.

`simulate` e solicitado como modo de `forge backtest` e deve ser distinguido por `mode=simulate` e prefixo `sim-`. Enquanto nao houver motor proprio, ele reaproveita o fluxo historico existente.

## Consequencias

- `bt-*` identifica runs `backtest`; `sim-*` identifica runs `simulate`.
- `mode=backtest` pode cobrir mais de um `subject`, desde que todos sejam avaliacoes historicas imutaveis.
- A CLI deve rejeitar `runId` cujo prefixo nao corresponda ao modo solicitado.
- Uma futura simulacao operacional com motor proprio precisa de nova decisao antes de substituir o fluxo historico compartilhado.
