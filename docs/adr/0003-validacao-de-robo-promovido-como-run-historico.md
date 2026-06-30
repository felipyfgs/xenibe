# ADR 0003: Validacao de robo promovido como run historico

Status: Aceita
Data: 2026-06-30

## Contexto

Depois que um candidato vencedor vira um robo promovido executavel, o Forge precisa validar esse robo em novos dados sem gerar candidatos a partir de `search-scope.yml`.

O resultado dessa validacao ainda e uma avaliacao historica imutavel, portanto pertence ao mesmo conceito de `run` decidido no ADR 0001.

## Decisao

Uma validacao de robo promovido deve gravar um novo run `bt-*` em:

`experiment/<experiment>/runs/<bt-run-id>/`

A interface CLI canonica deve ser:

```bash
forge run validate-promoted <experiment> <source-run-id> --root <root> --json
```

O subcomando e intencionalmente separado de `forge run backtest`, porque `backtest` executa busca de candidatos via `search-scope.yml`, enquanto `validate-promoted` avalia um unico robo ja escolhido.

`validate-promoted` deve usar o `ingest.yml` atual do experimento no momento da validacao. Se o usuario quiser validar em outro ativo, timeframe ou periodo, deve preparar o experimento antes, por exemplo com `forge history download ...`, e entao rodar a validacao.

Esse run deve registrar que o assunto avaliado foi um robo promovido, nao uma busca de candidatos. Os artefatos devem apontar para a origem:

`promoted/<experiment>/<source-run-id>/robot.yml`

No minimo, `manifest.json` ou `inputs.json` devem expor:

- `subject`: `promoted-robot`;
- experimento de origem;
- run de origem da promocao;
- caminho do `robot.yml` usado;
- candidato/fingerprint do robo avaliado.

O run de validacao deve manter os artefatos canonicos de run, incluindo `candidates.jsonl` e `scoreboard.json`. Como nao ha busca, `candidates.jsonl` deve conter exatamente um candidato derivado do `robot.yml`, marcado com `subject=promoted-robot`, e o `scoreboard.json` deve ranquear esse unico candidato.

Runs de busca por `search-scope.yml` devem declarar `subject=candidate-search`. Runs de validacao de robo promovido devem declarar `subject=promoted-robot`. Ambos continuam com `mode=backtest`.

A validacao deve usar a estrategia e a configuracao de risco gravadas em `robot.yml`. O `ingest.yml` atual define os dados da prova; o `robot.yml` define o comportamento operacional validado.

`validate-promoted` deve classificar o resultado usando o target gravado em `robot.yml`, que representa a promessa usada para promover o robo. O `target` atual de `experiment.yml` nao deve redefinir silenciosamente a regua de sucesso de um robo ja promovido.

Se o `robot.yml` contiver uma politica de `horizon-validation` habilitada, `validate-promoted` deve reaplicar essa politica nos dados atuais. Se a promocao nao usou horizonte, a validacao promovida nao deve buscar `horizon-validation` no `search-scope.yml` atual.

`validate-promoted` deve respeitar o contrato de execucao gravado no robo. Se o `ingest.yml` atual for incompativel com o timeframe/engine do robo, a validacao deve falhar com erro estruturado em vez de adaptar silenciosamente. O novo run deve registrar o payout usado na validacao.

## Consequencias

- `run show`, `run validate`, `report show` e `run compare` continuam operando sobre o mesmo catalogo de runs.
- O Forge evita criar uma arvore paralela de validacoes neste momento.
- Validadores e relatorios existentes podem ser reaproveitados com adaptacoes minimas para deixar claro que nao houve busca.
- O mesmo prefixo `bt-*` continua valido porque a validacao e historica e imutavel.
- A validacao pode ser feita em dados diferentes do run de promocao, desde que o `ingest.yml` atual aponte para esses dados.
- Alterar `risk.yml` no experimento depois da promocao nao muda a identidade do robo promovido ja gravado.
- Alterar `experiment.yml:target` depois da promocao nao muda o criterio de validacao do robo promovido ja gravado.
- Alterar `search-scope.yml:horizon-validation` depois da promocao nao muda a politica de horizonte de um robo promovido ja gravado.
- Alterar timeframe ou engine sem criar um novo robo promovido nao deve ser permitido por adaptacao silenciosa.
- Relatorios precisam deixar claro se o run e uma busca por `search-scope` ou uma validacao de `promoted-robot`.
