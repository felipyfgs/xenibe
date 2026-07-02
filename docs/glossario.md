# Glossario Xenibe

## Run

Avaliacao historica imutavel de uma configuracao de experimento sobre candles historicos. Runs de backtest usam `runId` com prefixo `bt-`; runs em modo `simulate` usam prefixo `sim-`.

## Subject

Campo que descreve o que um run avaliou. Valores canonicos iniciais: `candidate-search` para busca via `search-scope.yml` e `promoted-robot` para validacao de um `robot.yml` promovido.

## Backtest

Execucao historica reprodutivel de candidatos de estrategia sobre candles ja conhecidos. Gera artefatos imutaveis como `manifest.json`, `inputs.json`, `candidates.jsonl`, `scoreboard.json`, `metrics.json` e `report.md`.

## Validacao de Robo Promovido

Backtest historico imutavel que avalia um unico `robot.yml` promovido, sem gerar candidatos a partir de `search-scope.yml`. O resultado e gravado como um novo run `bt-*` no experimento e deve declarar `subject=promoted-robot`. A validacao promovida ainda nao esta exposta como comando publico compacto.

## Status

Estado de processamento de um registro, como `pending`, `tested` ou `skipped-duplicate`. Nao deve expressar resultado de negocio.

## Classification

Resultado de avaliacao de um candidato ou robo, como `winner`, `approved`, `rejected` ou `skipped`.

## Reason

Codigo que explica por que uma classificacao ocorreu, como `target-hit`, `positive-net-profit` ou `target-not-hit`.

## SearchState

Motivo de encerramento de um run de busca de candidatos. Nao se aplica a validacao de robo promovido.

## Simulate

Modo solicitado por `forge backtest <experiment> --mode simulate`. Usa o mesmo fluxo historico atual, registra `mode=simulate` e exige `runId` com prefixo `sim-`.

## Experiment

Diretorio versionavel que declara hipotese, alvo, ingestao de dados e escopo de busca. Um experimento pode gerar varios runs historicos.

## Candidate

Combinacao concreta de componentes de estrategia gerada a partir do `search-scope.yml` e avaliada em um run.

## Robo Promovido

Snapshot imutavel e executavel de um candidato vencedor. Deve conter origem, fingerprints, componentes, parametros, configuracao de risco efetiva, contrato de execucao, target de promocao, politica de horizonte quando aplicavel, score e metricas de promocao suficientes para permitir validacoes futuras sem gerar novos candidatos a partir de `search-scope.yml`. O local canonico e `promoted/<robot-id>/robot.yml`, com `robot-id` inicial em `<experiment>--<run-id>`.

## Robot.yml

Arquivo YAML versionado (`schema-version: 1`) que materializa um robo promovido. Usa chaves em kebab-case e secoes `robot`, `source`, `strategy`, `risk`, `execution` e `promotion`.
