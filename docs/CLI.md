# CLI - Forge

## Visão geral

O CLI `forge` deve operar sobre a pasta raiz de artefatos `forge/`. Essa pasta não é pacote Python e não deve conter lógica de implementação.

A implementação do CLI deve ficar em `/root/dev/xenibe/src/forge`, enquanto o núcleo reutilizável do domínio deve ficar em `/root/dev/xenibe/src/xenibe`.

O CLI deve seguir o estilo do OpenSpec: comandos claros, artefatos auditáveis, `--json`, validação e fluxos de promoção e arquivamento.

## Opções globais

```bash
forge --help
forge --version
forge <command> --json
forge <command> --root forge
forge <command> --no-color
```

| Opção | Descrição |
| --- | --- |
| `--root <path>` | Raiz de artefatos, padrão `forge`. |
| `--json` | Saída estruturada para automação. |
| `--no-color` | Desabilita cores. |
| `--yes` | Confirma ações sensíveis. |
| `--dry-run` | Simula sem enviar ordem ou alterar artefatos. |

## Contrato JSON para agentes IA

Todo comando com `--json` deve retornar `nextActions`.

Formato mínimo:

```json
{
  "status": [
    {"severity": "info", "code": "ok", "message": "Comando executado"}
  ],
  "data": {},
  "nextActions": [
    {
      "label": "Ver detalhes do run",
      "command": "forge run show idx-m1-soros-reversal bt-20260628-120000 --json"
    }
  ]
}
```

Regras:

- `status` deve existir em sucesso e erro;
- `data` deve conter o payload estruturado do comando;
- `nextActions` deve orientar o próximo passo autônomo do agente;
- em erro, `nextActions` deve sugerir correção ou diagnóstico;
- comandos que criam runs devem retornar o caminho dos artefatos.

## Estrutura criada pelo CLI

### `forge init`

Cria apenas a estrutura de artefatos:

```bash
forge init
forge init --root forge
```

Resultado:

```text
forge/
  config.yml
  promoted/
  archived/
```

O comando não cria módulos Python, `__init__.py`, `cli/`, `core/`, `providers/`, `strategies/` ou `backtest/` dentro de `forge`.

## Organização da implementação

A implementação deve ser organizada por feature em `src/forge`, com nomes simples de arquivos e sem `_` em nomes compostos.

```text
src/forge/
  cli.py
  experiment/
    command.py
    service.py
    schema.py
  run/
    command.py
    service.py
    schema.py
  promote/
    command.py
    service.py
  archive/
    command.py
    service.py
  report/
    command.py
    service.py
  validate/
    command.py
    service.py
```

O CLI pode importar regras de domínio de `src/xenibe`, por exemplo:

```text
src/xenibe/
  backtest/
    engine.py
  risk/
    manager.py
  provider/
    ebinex.py
  strategy/
    registry.py
```

Exemplos de nomes a evitar:

- `backtest_engine.py`;
- `risk_manager.py`;
- `strategy_registry.py`;
- `provider_ebinex.py`.

Preferir:

- `backtest/engine.py`;
- `risk/manager.py`;
- `strategy/registry.py`;
- `provider/ebinex.py`.

## Comandos principais

```text
forge init
forge experiment new
forge experiment list
forge experiment show
forge experiment validate
forge run backtest
forge run simulate
forge run show
forge run list
forge run validate
forge assets list
forge payout get
forge history download
forge report generate
forge compare runs
forge promote run
forge promote experiment
forge archive experiment
forge export run
forge validate
```

## Experimentos

### `forge experiment new <nome>`

Cria um experimento descritivo dentro de `forge/<nome>/`.

```bash
forge experiment new idx-m1-soros-reversal
forge experiment new btc-m1-payout-filter --asset BTCUSDT --timeframe M1
```

Estrutura criada:

```text
forge/idx-m1-soros-reversal/
  experiment.yml
  ingest.yml
  searchscope.yml
  provider.yml
  risk.yml
  report.yml
  notes.md
  runs/
```

### `forge experiment list`

```bash
forge experiment list
forge experiment list --json
```

Mostra experimentos ativos, promovidos e arquivados.

### `forge experiment show <nome>`

```bash
forge experiment show idx-m1-soros-reversal
forge experiment show idx-m1-soros-reversal --json
```

Mostra objetivo, status, estratégia referenciada, provider, risco e runs.

### `forge experiment validate <nome>`

```bash
forge experiment validate idx-m1-soros-reversal
```

Valida arquivos YAML, campos obrigatórios, referências externas, risco e consistência temporal.

## Runs

### `forge run backtest <experimento>`

Executa backtest usando a lógica externa ao `forge` e grava artefatos em `runs/<run-id>/`.

```bash
forge run backtest idx-m1-soros-reversal
forge run backtest idx-m1-soros-reversal --from 2026-01-01 --to 2026-06-01
forge run backtest idx-m1-soros-reversal --json
```

Saída esperada:

```text
Backtest started
Experiment: idx-m1-soros-reversal
Run ID: bt-20260628-120000
Artifacts: forge/idx-m1-soros-reversal/runs/bt-20260628-120000/
```

Artefatos esperados:

```text
forge/<experimento>/runs/<run-id>/
  manifest.json
  config-snapshot.yml
  inputs.json
  candidates.jsonl
  candles.sample.jsonl
  signals.jsonl
  orders.jsonl
  trades.jsonl
  blocks.jsonl
  equity.jsonl
  metrics.json
  report.md
  logs.jsonl
```

### `forge run simulate <experimento>`

Roda execução simulada em modo paper e grava um run.

```bash
forge run simulate idx-m1-soros-reversal
forge run simulate idx-m1-soros-reversal --duration 2h
```

### `forge run list <experimento>`

```bash
forge run list idx-m1-soros-reversal
forge run list idx-m1-soros-reversal --json
```

Lista runs do experimento.

### `forge run show <experimento> <run-id>`

```bash
forge run show idx-m1-soros-reversal bt-20260628-120000
forge run show idx-m1-soros-reversal bt-20260628-120000 --json
```

Mostra métricas, período, trades, bloqueios, equity e arquivos do run.

### `forge run validate <experimento> <run-id>`

```bash
forge run validate idx-m1-soros-reversal bt-20260628-120000
```

Valida:

- existência do manifesto;
- snapshot de configuração;
- arquivos JSON/JSONL válidos;
- presença de métricas;
- consistência entre sinais, ordens e trades;
- campos anti-lookahead.

## Ativos

### `forge assets list`

Lista ativos disponíveis no provider configurado ou informado.

```bash
forge assets list --provider ebinex
forge assets list --provider ebinex --active-only
forge assets list --provider ebinex --json
```

Saída humana esperada:

```text
Symbol    Status    Payout    Timeframes
IDXUSDT   ACTIVE    96.0      M1,M5,M15
BTCUSDT   ACTIVE    90.0      M1,M5,M15
```

Esse comando consulta provider externo, mas não cria código em `forge`.

## Payout

### `forge payout get <symbol>`

```bash
forge payout get IDXUSDT --provider ebinex
forge payout get IDXUSDT --provider ebinex --min 85
```

Se o payout estiver abaixo do mínimo:

```text
Error: payout-below-minimum
Fix: escolha outro ativo ou reduza payout-min na configuração do experimento.
```

## Histórico

### `forge history download <experimento>`

Baixa ou referencia histórico e registra o artefato no experimento.

```bash
forge history download idx-m1-soros-reversal --days 30
forge history download idx-m1-soros-reversal --from 2026-01-01 --to 2026-06-01
forge history download idx-m1-soros-reversal --days all
```

A saída pode ser registrada como artefato em:

```text
forge/<experimento>/ingest.yml
forge/<experimento>/runs/<run-id>/inputs.json
```

Parâmetros:

| Parâmetro | Descrição |
| --- | --- |
| `--timeframe` | `M1`, `M5`, `M15`, `H1`, `D1`. |
| `--from` | Início do período. |
| `--to` | Fim do período. |
| `--days` | Quantidade de dias ou `all`. |
| `--out` | Caminho externo para dataset, se aplicável. |

## Relatórios

### `forge report generate <experimento> <run-id>`

```bash
forge report generate idx-m1-soros-reversal bt-20260628-120000
forge report generate idx-m1-soros-reversal bt-20260628-120000 --format markdown
forge report generate idx-m1-soros-reversal bt-20260628-120000 --format json
```

Relatório padrão:

```text
forge/<experimento>/runs/<run-id>/report.md
```

## Comparação

### `forge compare runs`

Compara runs de um ou mais experimentos.

```bash
forge compare runs idx-m1-soros-reversal/bt-20260628-120000 idx-m1-soros-reversal/bt-20260629-090000
forge compare runs exp-a/run-1 exp-b/run-2 --metric net-pnl
```

## Promoção

### `forge promote run <experimento> <run-id>`

Promove um run para `forge/promoted/`.

```bash
forge promote run idx-m1-soros-reversal bt-20260628-120000 --reason "melhor relação winrate/drawdown"
```

Destino:

```text
forge/promoted/idx-m1-soros-reversal/
  promotion.yml
  runs/bt-20260628-120000/
```

### `forge promote experiment <experimento>`

Promove o experimento inteiro.

```bash
forge promote experiment idx-m1-soros-reversal --run bt-20260628-120000
```

## Arquivamento

### `forge archive experiment <experimento>`

Arquiva um experimento encerrado.

```bash
forge archive experiment idx-m1-soros-reversal --reason "substituído por nova variação"
forge archive experiment idx-m1-soros-reversal --yes
```

Destino:

```text
forge/archived/YYYY-MM-DD-idx-m1-soros-reversal/
  archive.yml
  ...artefatos do experimento...
```

## Exportação

### `forge export run <experimento> <run-id>`

```bash
forge export run idx-m1-soros-reversal bt-20260628-120000 --format csv --out exports/backtest.csv
forge export run idx-m1-soros-reversal bt-20260628-120000 --format json --out exports/backtest.json
```

Formatos planejados:

- `json`;
- `csv`;
- `parquet`;
- `markdown`;
- `html`.

## Validação geral

### `forge validate`

```bash
forge validate
forge validate --experiment idx-m1-soros-reversal
forge validate --run idx-m1-soros-reversal/bt-20260628-120000
forge validate --all
```

Valida estrutura de artefatos, YAML, JSON, JSONL, runs e campos obrigatórios.

## Estrutura esperada de `experiment.yml`

```yaml
id: idx-m1-soros-reversal
name: IDX M1 Soros Reversal
status: active
objective: Validar reversão M1 no IDXUSDT com Soros N1.
created-at: 2026-06-28T00:00:00Z
asset: IDXUSDT
timeframe: M1
target:
  metric: net-pnl
  operator: ">="
  value: 200
  stop-on-first-target: true
run-defaults:
  mode: backtest
  tie-policy: refund
```

## Estrutura esperada de `ingest.yml`

```yaml
data:
  provider: ebinex
  asset: IDXUSDT
  timeframe: M1
  from: 2026-01-01T00:00:00Z
  to: 2026-06-01T00:00:00Z
  source: remote
validation:
  require-complete-candles: true
  reject-gaps: true
  timezone: UTC
```

## Estrutura esperada de `searchscope.yml`

```yaml
search:
  components:
    indicators:
      enabled: true
      role: feature
    filters:
      enabled: true
      role: prefilter
    triggers:
      enabled: true
      role: entry
    decision:
      enabled: true
      role: final-decision
    candlepatterns:
      enabled: true
      role: price-action
    marketcontext:
      enabled: true
      role: context
  indicators:
    rsi:
      period: [7, 14, 21]
    ema:
      fast: [5, 9, 12]
      slow: [21, 34, 55]
  limits:
    mode: dynamic
    resolved-before-run: true
    max-combinations: null
    max-runtime: null
```

## Estrutura esperada de `risk.yml`

```yaml
risk:
  bankroll: 1000
  stop-loss-pct: 0.10
  stop-win-pct: 0.20
  stake-divisor: 4
  min-payout: 85
  max-open-trades: 1
management:
  mode: soros
  soros:
    enabled: true
    levels: 1
    reset-on-loss: true
  martingale:
    enabled: false
    max-levels: 0
    factor: 2.0
```

## Estrutura esperada de `manifest.json`

```json
{
  "runId": "bt-20260628-120000",
  "experiment": "idx-m1-soros-reversal",
  "type": "backtest",
  "status": "completed",
  "startedAt": "2026-06-28T12:00:00Z",
  "finishedAt": "2026-06-28T12:01:10Z",
  "artifacts": [
    "config-snapshot.yml",
    "candidates.jsonl",
    "signals.jsonl",
    "trades.jsonl",
    "blocks.jsonl",
    "metrics.json",
    "report.md"
  ]
}
```

## Mensagens de erro esperadas

| Código | Quando ocorre |
| --- | --- |
| `experiment-not-found` | Experimento não existe em `forge/`. |
| `run-not-found` | Run não existe em `runs/<run-id>/`. |
| `invalid-artifact-tree` | Estrutura do experimento está inválida. |
| `invalid-yaml` | Arquivo YAML inválido. |
| `invalid-json` | Arquivo JSON ou JSONL inválido. |
| `asset-closed` | Ativo não está aberto. |
| `payout-below-minimum` | Payout menor que o mínimo configurado. |
| `entry-window-closed` | Restam 5 segundos ou menos para fechamento da vela. |
| `stop-loss-reached` | Stop Loss da sessão foi atingido. |
| `stop-win-reached` | Stop Win da sessão foi atingido. |
| `stake-exceeds-risk-limit` | Stake calculado excede risco restante. |
| `history-gap-detected` | Histórico tem lacunas. |
| `lookahead-detected` | Estratégia tentou acessar dado futuro. |
| `provider-not-connected` | Provider não está conectado. |
| `order-rejected` | Broker rejeitou a ordem. |
| `settlement-timeout` | Resultado não chegou no tempo esperado. |

## Boas práticas

- Manter `forge/` somente com artefatos.
- Não salvar código Python dentro de `forge/`.
- Criar um experimento por hipótese clara.
- Criar um `run-id` novo para cada execução.
- Nunca sobrescrever um run existente.
- Sempre gravar `config-snapshot.yml`.
- Sempre registrar bloqueios em `blocks.jsonl`.
- Promover somente runs auditáveis.
- Arquivar experimentos encerrados em `forge/archived/`.
- Usar `--json` em automações.
