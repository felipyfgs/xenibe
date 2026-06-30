# ADR 0002: Robo promovido como snapshot executavel

Status: Aceita
Data: 2026-06-30

## Contexto

O fluxo atual de promocao grava apenas `promotion.yml` com experimento de origem, run de origem, motivo, timestamp e metricas selecionadas. Esse artefato aponta para um resultado, mas nao materializa um robo reexecutavel.

Isso impede um backtest simples de validacao sem `search-scope.yml`, porque o Forge precisa voltar ao run original para descobrir qual candidato foi vencedor e quais componentes/parametros formavam a estrategia.

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
- metadata de promocao, como motivo e timestamp.

O snapshot executavel deve viver no caminho ja usado pela promocao:

`promoted/<experiment>/<run-id>/robot.yml`

O arquivo `promotion.yml` permanece como metadata de promocao. O identificador publico inicial do robo promovido e o par `<experiment>/<run-id>`, evitando uma nova camada global de nomes ate haver necessidade concreta.

`robot.yml` deve ser YAML versionado com `schema-version: 1`, chaves em kebab-case e secoes top-level:

- `robot`;
- `source`;
- `strategy`;
- `risk`;
- `execution`;
- `promotion`.

## Consequencias

- Promocao deixa de ser apenas um ponteiro para metadata e passa a criar um contrato reexecutavel de estrategia, risco e execucao.
- Validacoes futuras podem rodar um backtest direto contra o snapshot promovido, sem gerar candidatos a partir de `search-scope.yml`.
- O snapshot promovido deve ser tratado como imutavel e user-owned.
- O caminho existente `promoted/<experiment>/<run-id>/` continua canonico para localizar promocoes.
- O formato YAML do robo deve seguir kebab-case, assim como os demais contratos YAML do Forge.
- Mudancas no formato do snapshot exigem decisao/versionamento explicito.
