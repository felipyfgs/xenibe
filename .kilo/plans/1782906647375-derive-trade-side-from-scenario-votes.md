# Plano: Derivar Direção de Trade por Votos de Cenário

## Objetivo

Criar a mudança OpenSpec `derive-trade-side-from-scenario-votes` para remover direção fixa (`side: call` / `side: put`) dos triggers direcionais e fazer cada componente votar `call` ou `put` a partir do cenário observado.

O resultado esperado é que o `search-scope.yml` descreva condições de mercado, não uma direção predefinida. A decisão entra somente quando os votos direcionais dos componentes concordam.

## Decisões Confirmadas

- Rejeitar `side` fixo em novos scopes para triggers direcionais.
- Não introduzir `side: auto`.
- A direção deve ser inferida pelo componente a partir do candle/cenário.
- Manter a regra atual de consenso do compilador:
  - votos concordantes geram sinal;
  - votos conflitantes bloqueiam entrada;
  - nenhum voto direcional bloqueia entrada.
- Não preservar compatibilidade legada para novos scopes que declarem `side` nesses triggers.

## Contexto Técnico Atual

- `src/xenibe/strategy/compiler.py` já coleta `side_votes` e rejeita conflito com `side-conflict`.
- `src/xenibe/analysis/registry.py` já possui vários componentes que votam dinamicamente, como `trend`, `support-resistance-zone`, `pullback-to-ema`, `range-break-retest`, `trend-pullback`, `sr-reversal`, `multi-timeframe-alignment` e `rsi-zone`.
- Os triggers `engulfing`, `pinbar-rejection` e `momentum-close` ainda dependem de parâmetro fixo `side`.
- `src/xenibe/strategy/components.py` exige `side` para esses triggers no schema atual.
- O experimento `idx-m1-soros-reversal` chegou perto do alvo com escopo forçado em `call`, mas isso enviesou a busca e não representa a intenção de operar conforme cenário.

## OpenSpec A Criar

Change name sugerido: `derive-trade-side-from-scenario-votes`

Capabilities afetadas sugeridas:

- `strategy-candidate-generation` ou capability nova equivalente para semântica de componentes e decisão.
- Se não existir spec principal apropriada, criar delta spec nova para estratégia/decisão direcional.

## Artefatos Esperados

### proposal.md

Deve explicar:

- Problema: direção fixa no `search-scope.yml` transforma lado (`call`/`put`) em parâmetro de busca, não em resultado de análise.
- Objetivo: componentes votam lado conforme cenário.
- Impacto: novos scopes com `side` fixo em triggers direcionais devem falhar validação.
- Benefício: busca passa a avaliar cenários, reduzindo viés artificial por direção.

### design.md

Deve cobrir:

- Como cada trigger infere direção:
  - `momentum-close`: candle com corpo forte para cima vota `call`; corpo forte para baixo vota `put`.
  - `pinbar-rejection`: pavio inferior dominante vota `call`; pavio superior dominante vota `put`.
  - `engulfing`: bullish engulfing vota `call`; bearish engulfing vota `put`.
- Como o compilador mantém consenso:
  - um único lado votado e score suficiente: entra;
  - lados conflitantes: `side-conflict`, sem sinal;
  - nenhum lado: `no-side-vote`, sem sinal.
- Como tratar migração:
  - rejeitar `side` nesses triggers com mensagem clara;
  - atualizar scopes ativos removendo `side`.
- Como evitar `side: auto`:
  - ausência de `side` significa componente derivar direção por regra própria.

### specs

Requisitos sugeridos:

- O sistema SHALL inferir voto direcional de triggers suportados a partir do cenário.
- O sistema SHALL rejeitar `side` fixo em novos scopes para `momentum-close`, `pinbar-rejection` e `engulfing`.
- O sistema SHALL bloquear entrada quando componentes aprovados votarem lados conflitantes.
- O sistema SHALL bloquear entrada quando nenhum componente aprovado votar lado direcional.
- O sistema SHALL permitir que componentes não direcionais filtrem cenário sem emitir lado.

Cenários obrigatórios:

- Momentum bullish gera `call` sem parâmetro `side`.
- Momentum bearish gera `put` sem parâmetro `side`.
- Pinbar com pavio inferior gera `call`.
- Pinbar com pavio superior gera `put`.
- Engulfing bullish gera `call`.
- Engulfing bearish gera `put`.
- Votos `call` e `put` no mesmo candidato geram `side-conflict` e não criam ordem.
- Scope com `side` em trigger direcional falha validação.

### tasks.md

1. Atualizar schema de `COMPONENT_PARAMETER_RULES` para remover/rejeitar `side` em `momentum-close`, `pinbar-rejection` e `engulfing`.
2. Adicionar validação/mensagem clara para configs que ainda declarem `side` nesses triggers.
3. Atualizar `evaluate_momentum_close` para inferir `call`/`put` pela direção do candle quando `body_ratio >= body-min-atr`.
4. Atualizar `evaluate_pinbar` para inferir lado por pavio dominante conforme `min-wick-ratio`.
5. Atualizar `evaluate_engulfing` para inferir lado por padrão bullish/bearish sem `side`.
6. Garantir que componentes sem direção continuem funcionando como filtros.
7. Adicionar testes unitários para votos dinâmicos de `call`, `put`, sem sinal e conflito.
8. Atualizar fixtures/search scopes para remover `side` desses triggers.
9. Rodar `forge check idx-m1-soros-reversal --root forge --json` após migração do scope.
10. Rodar backtest real e comparar com runs anteriores, sem promover automaticamente.
11. Rodar `PYTHONPATH=src python3 -m unittest discover -s tests`.

## Riscos

- Remover `side` muda a quantidade de candidatos e pode invalidar scopes antigos.
- Triggers dinâmicos podem aumentar frequência de sinais se combinados com poucos filtros.
- O win-rate pode melhorar ou piorar; esta mudança corrige o modelo, não garante performance.
- Alguns testes/fixtures podem depender de `side` fixo e precisam ser migrados.

## Validação Recomendada

- Testes unitários de `evaluate_candidate_decision` para consenso e conflito.
- Testes de validação de YAML rejeitando `side` fixo.
- Testes de cada trigger inferindo lado corretamente.
- `forge check idx-m1-soros-reversal --root forge --json`.
- Backtest com candles reais já baixados no root `forge`.
- Comparar resultado contra:
  - `bt-20260701-114046`
  - `bt-20260701-114641`

## Fora Do Escopo

- Criar `side: auto`.
- Promover run automaticamente.
- Alterar payout fixo do backtest.
- Garantir que a estratégia atinja `win-rate >= 0.6` apenas por esta mudança.
