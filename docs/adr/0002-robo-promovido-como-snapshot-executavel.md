# ADR 0002: Robo promovido como snapshot executavel

Status: Aceita
Data: 2026-06-30

## Contexto

A promocao precisa materializar um robo reexecutavel. Sem um snapshot completo, o Forge teria que voltar ao run original para descobrir qual candidato foi vencedor e quais componentes/parametros formavam a estrategia.

## Decisao

Um robo promovido deve ser um snapshot imutavel e executavel do candidato vencedor.

O snapshot deve conter, no minimo:

- identificador do robo promovido;
- experimento de origem;
- run de origem;
- candidato de origem;
- `candidateFingerprint` e, quando aplicavel, `evaluationFingerprint`;
- componentes e parametros executaveis do candidato;
- configuracao de risco efetiva usada na promocao;
- contrato de execucao usado na promocao, incluindo engine, timeframe, entrada, expiracao, politica de empate e premissa de payout;
- target efetivo usado para classificar a promocao;
- politica efetiva de `horizon-validation`, quando habilitada na promocao;
- metricas que justificaram a promocao;
- motivo e timestamp da promocao.

O snapshot executavel deve viver diretamente no catalogo live-readable de robos promovidos:

`promoted/<robot-id>/robot.yml`

O `robot-id` canonico inicial e `<experiment>--<run-id>`. Motivo, timestamp, origem, metricas e score ficam dentro de `robot.yml`.

`robot.yml` deve ser YAML versionado com `schema-version: 1`, chaves em kebab-case e secoes top-level:

- `robot`;
- `source`;
- `strategy`;
- `risk`;
- `execution`;
- `promotion`.

## Consequencias

- Promocao cria um contrato reexecutavel de estrategia, risco e execucao.
- Validacoes futuras podem rodar um backtest direto contra o snapshot promovido, sem gerar candidatos a partir de `search-scope.yml`.
- O snapshot promovido deve ser tratado como imutavel e user-owned.
- `promoted/` e o catalogo que o motor live deve varrer; cada filho direto e um robo promovido.
- O formato YAML do robo deve seguir kebab-case, assim como os demais contratos YAML do Forge.
- Mudancas no formato do snapshot exigem decisao/versionamento explicito.
