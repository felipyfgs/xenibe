# ADR 0004: Vocabulario publico de estados de run

Status: Aceita
Data: 2026-06-30

## Contexto

Os artefatos atuais misturam conceitos diferentes nos campos `status`, `classification`, `reason` e `searchState`. Por exemplo, `target-hit` pode aparecer como status de candidato, reason e estado de encerramento da busca.

Essa sobreposicao dificulta diferenciar runs de busca por `search-scope` de runs de validacao de um robo promovido.

## Decisao

Separar o vocabulario publico da seguinte forma:

- `status`: estado de processamento do registro, como `pending`, `tested` ou `skipped-duplicate`;
- `classification`: resultado de avaliacao do candidato/robo, como `winner`, `approved`, `rejected` ou `skipped`;
- `reason`: explicacao legivel por maquina para a classificacao, como `target-hit`, `positive-net-profit`, `target-not-hit`, `duplicate-evaluation` ou `horizon-validation-failed`;
- `searchState`: motivo de encerramento apenas de runs com busca de candidatos, como `target-hit`, `stagnation`, `max-rounds` ou `limits-exhausted`.

Runs de validacao de robo promovido nao devem usar `searchState`, pois nao executam busca.

O campo `subject` diferencia os contratos:

- `candidate-search`: run que gera e avalia candidatos a partir de `search-scope.yml`;
- `promoted-robot`: run que avalia um unico `robot.yml` promovido.

## Consequencias

- `target-hit` deixa de ser status de processamento de candidato e passa a ser reason/classificacao de resultado ou estado de encerramento de busca, dependendo do contexto.
- Relatorios e validadores devem distinguir `subject=candidate-search` de `subject=promoted-robot`.
- O vocabulario fica mais previsivel para consumidores externos dos artefatos JSON/JSONL.
