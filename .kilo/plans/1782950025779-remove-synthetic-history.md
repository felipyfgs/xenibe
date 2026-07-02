# Plano: Remover Historico Sintetico do Forge

## Objetivo

Criar e implementar a mudanca OpenSpec `remove-synthetic-history` para remover completamente o suporte a candles/historico sintetico no Forge/Xenibe.

Resultado esperado: `forge backtest` e `forge backtest --mode simulate` sempre exigem historico configurado, parseavel e carregado a partir do `ingest.yml`. Nao deve existir fallback para candles default gerados em codigo.

## Decisoes Confirmadas

- Remocao completa, nao apenas desabilitacao operacional.
- `--allow-synthetic` deve deixar de ser uma opcao valida.
- Runs novos devem registrar `execution.dataSource: configured-history` quando houver historico valido.
- Runs/artefatos com `synthetic-default` devem passar a falhar validacao.
- Artefatos gerados em `forge/` continuam sendo propriedade do usuario; nao deletar ou editar runs antigos automaticamente.
- O run local `forge/experiment/idx-m1-soros-reversal/runs/bt-20260701-094552` contem `synthetic-default` e deve ficar invalido apos a mudanca se for validado.

## Mapeamento Verificado

- `src/forge/run/service.py` define `default_candles()`, aceita `allow_synthetic`, cria `CandleLoad(..., "synthetic-default")`, marca `history.synthetic`, adiciona a limitacao `synthetic-default-candles` e grava `execution.dataSource`.
- `src/forge/workflow.py` reconhece `--allow-synthetic`, remove a flag dos argumentos e repassa `allow_synthetic` para `run_service.run_backtest()`.
- `src/forge/catalog.py` documenta `--allow-synthetic` no help de `forge backtest`.
- `src/xenibe/artifacts/store.py` valida runs, mas hoje nao rejeita `synthetic-default` em `manifest.json` ou `inputs.json`.
- `tests/test_cli.py` e `tests/test_forge_features.py` usam `--allow-synthetic` em fluxos de backtest/simulate.
- `tests/fixtures/valid-run/bt-20260101-000000/manifest.json` e `inputs.json` usam `synthetic-default`; esse fixture precisa ser convertido para historico configurado ou virar fixture invalido.
- `openspec/specs/forge-contract-integrity/spec.md` contem o requisito ativo `Synthetic candle data is explicit`, que permite opcao sintetica.
- `.kilo/skills/forge-run/SKILL.md` ainda recomenda `--allow-synthetic` para smoke test/diagnostico.
- Referencias em `openspec/changes/archive/...` e planos antigos sao historicas; nao altera-las salvo pedido explicito.

## OpenSpec A Criar

Change name sugerido: `remove-synthetic-history`.

Artefatos esperados:

- `openspec/changes/remove-synthetic-history/proposal.md`
- `openspec/changes/remove-synthetic-history/design.md`
- `openspec/changes/remove-synthetic-history/tasks.md`
- `openspec/changes/remove-synthetic-history/specs/forge-contract-integrity/spec.md`

Conteudo esperado da delta spec:

- Remover ou substituir o requisito ativo `Synthetic candle data is explicit`.
- Adicionar requisito `Backtests require configured real history`.
- Cenario: experimento sem candles parseaveis falha com `missing-artifact` e oferece apenas `forge data download` como proxima acao operacional.
- Cenario: `forge backtest <experiment> --allow-synthetic` falha como opcao removida/nao suportada e orienta baixar/configurar historico real.
- Cenario: backtest bem-sucedido registra `execution.dataSource: configured-history`.
- Cenario: `simulate` tambem exige historico real, preservando apenas diferenca de `mode=simulate` e prefixo `sim-`.
- Cenario: run com `synthetic-default` em `manifest.execution.dataSource`, `inputs.execution.dataSource`, `inputs.history.dataSource`, `inputs.history.synthetic` ou limitacao `synthetic-default-candles` falha validacao.

## Tarefas De Implementacao

1. Criar a mudanca OpenSpec `remove-synthetic-history` em uma arvore separada da mudanca ativa `derive-trade-side-from-scenario-votes`.
2. Atualizar a delta spec de `forge-contract-integrity` conforme os cenarios acima.
3. Em `src/forge/run/service.py`, remover `default_candles()`.
4. Em `src/forge/run/service.py`, remover o parametro `allow_synthetic` de `_load_candles_or_error()`, `_load_run_setup()` e `run_backtest()`.
5. Em `_load_candles_or_error()`, quando nao houver candles parseaveis, retornar somente erro `missing-artifact` com next action para `forge data download`; remover mensagem e next action com `--allow-synthetic`.
6. Em `_load_run_setup()`, manter `history_context["dataSource"] = "configured-history"` somente quando `load_history_candles()` retornar candles.
7. Em `_run_limitations()`, remover o bloco que adiciona `synthetic-default-candles`.
8. Em `src/forge/workflow.py`, remover o parsing permissivo de `--allow-synthetic`.
9. Em `src/forge/workflow.py`, adicionar rejeicao explicita para `--allow-synthetic` com `unknown-command` ou codigo existente equivalente, mensagem de opcao removida e next action para `forge data download`.
10. Em `src/forge/workflow.py`, atualizar a chamada para `run_service.run_backtest()` com a nova assinatura.
11. Em `src/forge/catalog.py`, remover `--allow-synthetic` do help de `forge backtest`.
12. Em `src/xenibe/artifacts/store.py`, adicionar validacao de runs para rejeitar sinais sinteticos persistidos.
13. A validacao deve inspecionar pelo menos `manifest.json:execution.dataSource`, `inputs.json:execution.dataSource`, `inputs.json:history.dataSource`, `inputs.json:history.synthetic` e `inputs.json:limitations[].code`.
14. Se encontrar `synthetic-default`, `synthetic: true` ou `synthetic-default-candles`, retornar `ValidationIssue("invalid-artifact", ...)` com caminho preciso e mensagem orientando recriar o run com historico real.
15. Atualizar `tests/fixtures/valid-run/bt-20260101-000000` para representar `configured-history` em `manifest.json` e `inputs.json`.
16. Adicionar teste de validacao que copia um run valido, injeta `synthetic-default` e confirma que `validate_run_dir()` reporta `invalid-artifact`.
17. Atualizar `tests/test_cli.py` para que backtest sem historico continue falhando com `missing-artifact`, mas sem next action contendo `--allow-synthetic`.
18. Atualizar `tests/test_cli.py` para preparar historico real/configurado antes dos backtests que hoje usam `--allow-synthetic`.
19. Para testes sem provider injetavel, criar helper de teste que escreve CSV parseavel em `data/EURUSD_M1.csv` ou no diretorio `data/` conforme `ingest.yml`; incluir manifest quando o teste apontar `data.path` para CSV canonico.
20. Atualizar `tests/test_forge_features.py` para substituir `--allow-synthetic` por `forge data download ...` com `MockProvider` ou por helper de historico configurado.
21. Atualizar o teste de `simulate` para baixar/preparar historico real antes de executar `--mode simulate`.
22. Atualizar testes de config opcional malformada para criarem historico real suficiente antes de exercitar `risk.yml`, `provider.yml` ou `report.yml` invalidos, garantindo que o erro testado continue sendo `invalid-yaml`.
23. Atualizar `.kilo/skills/forge-run/SKILL.md` removendo todas as orientacoes de smoke test sintetico e substituindo por diagnostico de historico real via `forge data download`.
24. Remover referencias ativas a `synthetic-default`, `synthetic-default-candles`, `default_candles` e `--allow-synthetic` de codigo, testes ativos, fixtures ativas, skill e spec principal.
25. Nao editar automaticamente `forge/experiment/.../runs/*`, `openspec/changes/archive/*` ou planos antigos; eles sao historico/artefatos do usuario.

## Riscos

- `forge status --root forge --json` pode passar a reportar bloqueio se houver runs sinteticos antigos no root local.
- Fixtures que eram consideradas validas passam a ser invalidas se nao forem migradas.
- Testes que usavam synthetic fallback podem comecar a falhar antes de exercitar o comportamento pretendido; por isso precisam preparar historico real primeiro.
- Arquivos arquivados em `openspec/changes/archive` e planos antigos ainda podem conter texto sobre sintético; isso nao representa comportamento ativo.

## Validacao Recomendada

1. Rodar `PYTHONPATH=src python3 -m unittest discover -s tests`.
2. Rodar `PYTHONPATH=src python3 -m forge backtest idx-m1-soros-reversal --root forge --json` com historico real existente.
3. Rodar `PYTHONPATH=src python3 -m forge backtest idx-m1-soros-reversal --allow-synthetic --root forge --json` e confirmar falha clara.
4. Rodar `PYTHONPATH=src python3 -m forge check idx-m1-soros-reversal bt-20260701-094552 --root forge --json` e confirmar que run sintetico antigo falha validacao.
5. Rodar `PYTHONPATH=src python3 -m forge check idx-m1-soros-reversal --root forge --json` para confirmar que o experimento continua valido quando o historico real esta presente.
6. Fazer busca textual ativa por `allow-synthetic`, `synthetic-default`, `synthetic-default-candles` e `default_candles`; as sobras aceitaveis devem estar apenas em arquivos arquivados/historicos explicitamente fora de escopo.

## Fora Do Escopo

- Deletar, editar ou arquivar runs antigos em `forge/` automaticamente.
- Reescrever arquivos em `openspec/changes/archive`.
- Reescrever planos antigos em `.kilo/plans`.
- Garantir performance ou melhoria de resultado de backtest; esta mudanca corrige a origem de dados.
