# Arquitetura - Forge

## Correção de modelo

O `forge` da raiz do projeto não é uma pasta de lógica Python. Ele deve ficar em `/root/dev/xenibe/forge` como uma área de artefatos operacionais, no mesmo espírito organizacional de `/root/dev/xenibe/openspec`.

A lógica Python de estratégia, provider, backtest, risco e CLI deve viver em `/root/dev/xenibe/src`. O `forge/` da raiz guarda somente descrições de experimentos, configurações congeladas, execuções, relatórios, promoções e arquivados.

## Visão geral

A arquitetura passa a ter duas camadas separadas:

1. **Camada de execução e lógica**, em `src/forge` e `src/xenibe`.
2. **Camada de artefatos**, em `forge/` na raiz.

O `forge` é a fonte auditável dos experimentos e runs. Ele deve permitir reproduzir, comparar, promover ou arquivar resultados sem misturar código-fonte com saídas de laboratório.

## Organização do código-fonte

O código deve seguir uma organização limpa por feature em `/root/dev/xenibe/src`.

```text
src/
  forge/
    cli.py
    experiment/
      command.py
      model.py
      schema.py
      service.py
    run/
      command.py
      model.py
      schema.py
      service.py
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

  xenibe/
    candles/
      model.py
      window.py
      repo.py
      validate.py
    provider/
      base.py
      ebinex.py
      csv.py
      paper.py
    strategy/
      base.py
      context.py
      registry.py
      signal.py
    backtest/
      engine.py
      timeline.py
      settle.py
      metric.py
      guard.py
    risk/
      manager.py
      sizing.py
      soros.py
      martingale.py
      ledger.py
    execution/
      live.py
      schedule.py
      simulate.py
      reconcile.py
```

Regras de nomenclatura:

- organizar por feature antes de criar arquivos grandes;
- evitar nomes compostos com `_` em arquivos Python;
- preferir pastas por contexto e arquivos simples, como `risk/manager.py`, `backtest/engine.py`, `candles/window.py`;
- manter `/root/dev/xenibe/forge` apenas para artefatos;
- manter `/root/dev/xenibe/src/forge` como código da aplicação/CLI do laboratório;
- manter `/root/dev/xenibe/src/xenibe` como núcleo de domínio reutilizável.

## Bases estudadas

### `backtesting.py`

O estudo de `_stude/backtesting.py` mostrou conceitos úteis, como validação de OHLCV, warmup de indicadores, revelação progressiva e métricas. Porém, o modelo de `Strategy.next()` recebe a vela atual completa e não deve ser usado diretamente para Ebinex M1.

A lógica futura pode se inspirar nesses conceitos, mas os artefatos do resultado devem ser gravados em `forge/<experimento>/runs/<run-id>/`.

### `pyebinex`

O estudo de `_stude/pyebinex` mostrou que `EbinexClient` cobre autenticação, sessão, ativos, payout, histórico, envio de ordem e consulta de resultado.

O `forge` deve apenas registrar nos artefatos qual provider foi usado, quais parâmetros foram aplicados e quais respostas ou resultados foram observados. O código wrapper do provider deve ficar fora de `forge`.

### `OpenSpec`

O estudo de `_stude/OpenSpec` mostrou um padrão útil de pasta raiz com artefatos, configuração e arquivamento:

```text
openspec/
  config.yml
  specs/
  changes/
    archive/
```

O `forge` deve seguir a mesma filosofia: artefatos organizados, auditáveis e promovíveis, sem misturar implementação.

## Árvore proposta do `forge`

```text
forge/
  config.yml

  promoted/
    <nome-descritivo-do-experimento>/
      promotion.yml
      runs/
        <run-id>/
          manifest.json
          config-snapshot.yml
          metrics.json
          report.md

  archived/
    YYYY-MM-DD-<nome-descritivo-do-experimento>/
      archive.yml
      runs/
        <run-id>/

  <nome-descritivo-do-experimento>/
    experiment.yml
    ingest.yml
    searchscope.yml
    provider.yml
    risk.yml
    report.yml
    notes.md
    runs/
      <run-id>/
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

## Responsabilidade de cada item

| Item | Responsabilidade |
| --- | --- |
| `forge/config.yml` | Configuração global do laboratório de artefatos. |
| `forge/<experimento>/` | Espaço de trabalho de um experimento com nome descritivo. |
| `experiment.yml` | Identidade, objetivo, hipótese, meta, critério de parada, período, status e metadados do experimento. |
| `ingest.yml` | Configuração de dados históricos: ativo, timeframe, início, fim, provider, fonte e validação. |
| `searchscope.yml` | Espaço de busca: ferramentas, indicadores, padrões, contexto de mercado e ranges de parâmetros. |
| `provider.yml` | Provider usado, ambiente, credenciais referenciadas, ativo, timeframe e parâmetros de consulta. |
| `risk.yml` | Stop Loss, Stop Win, stake base, Soros, Martingale e limites. |
| `report.yml` | Configuração de relatórios, exportações e formatos. |
| `notes.md` | Observações humanas do experimento. |
| `runs/<run-id>/` | Artefatos imutáveis de uma execução específica. |
| `manifest.json` | Índice do run, comandos executados, timestamps e versões. |
| `config-snapshot.yml` | Snapshot completo da configuração usada no run. |
| `inputs.json` | Entradas resolvidas, como ativo, payout, banca, período e limites dinâmicos escolhidos pelo agente. |
| `candidates.jsonl` | Possibilidades testadas, com componentes de análise, parâmetros, status e métricas parciais. |
| `signals.jsonl` | Sinais gerados com `decisionTime` e `visibleUntil`. |
| `orders.jsonl` | Ordens planejadas, enviadas ou simuladas. |
| `trades.jsonl` | Resultados finais das operações. |
| `blocks.jsonl` | Entradas bloqueadas e seus motivos. |
| `equity.jsonl` | Evolução da banca e PnL. |
| `metrics.json` | Métricas finais do run. |
| `report.md` | Relatório legível do run. |
| `logs.jsonl` | Logs estruturados da execução. |
| `promoted/` | Experimentos ou runs promovidos para referência operacional. |
| `archived/` | Experimentos encerrados, movidos com data e manifesto de arquivamento. |

## O que não deve existir dentro de `/root/dev/xenibe/forge`

A pasta de artefatos `/root/dev/xenibe/forge` não deve conter:

- `__init__.py`;
- `__main__.py`;
- módulos Python de `cli`, `core`, `providers`, `strategies`, `risk` ou `backtest`;
- implementação de estratégia;
- implementação de provider;
- motor de backtest;
- ambiente virtual;
- dependências instaladas;
- caches de execução não auditáveis.

## Fluxo de dados e artefatos

```text
Código em src/forge e src/xenibe
  -> carrega configuração do experimento
  -> executa backtest, simulação ou coleta
  -> grava snapshot e eventos em forge/<experimento>/runs/<run-id>/
  -> gera métricas e relatório
  -> opcionalmente promove ou arquiva o experimento
```

## Fluxo de backtest

1. CLI recebe o nome do experimento.
2. CLI lê `forge/<experimento>/experiment.yml` e arquivos relacionados.
3. A lógica em `src/forge` e `src/xenibe` carrega histórico, estratégia, provider e risco.
4. O motor percorre candles M1 com janela causal.
5. Estratégia recebe somente candles fechados.
6. O agente resolve limites dinâmicos de busca e grava em `inputs.json`.
7. Risco aprova ou rejeita entrada.
8. Ordem aprovada é agendada para a próxima vela.
9. Liquidação ocorre no fechamento da próxima vela.
10. O run grava eventos em `signals.jsonl`, `orders.jsonl`, `trades.jsonl` e `blocks.jsonl`.
11. Se um `candidate` atingir a meta de `experiment.yml`, a busca para.
12. Métricas finais são gravadas em `metrics.json` e `report.md`.
13. O run concluído fica imutável.

## Fluxo de execução real futura

1. CLI recebe o experimento e abre novo `run-id`.
2. Lógica em `src/xenibe/provider` conecta no provider Ebinex.
3. Histórico fechado é sincronizado.
4. Scheduler identifica início da vela atual.
5. Estratégia analisa candles fechados até a vela anterior.
6. Risco valida payout, ativo, saldo, stop e tempo.
7. Provider envia ordem antes do bloqueio dos últimos 5 segundos.
8. Provider aguarda resultado via WebSocket ou REST.
9. Artefatos são gravados no diretório do run.
10. Run é encerrado, promovido ou arquivado.

## Integração com `pyebinex`

A integração com `pyebinex` deve ser representada nos artefatos por configuração e resultados, não por código dentro de `/root/dev/xenibe/forge`. O código de integração deve ficar em `src/xenibe/provider/ebinex.py`.

Operações que a lógica externa deve expor:

- listar ativos;
- consultar payout;
- verificar ativo aberto;
- buscar histórico completo;
- enviar ordem;
- acompanhar resultado;
- consultar histórico de ordens;
- verificar conexão e sessão;
- normalizar erros e rejeições.

Mapeamento esperado:

| Operação | Chamada em `pyebinex` |
| --- | --- |
| Conectar | `EbinexClient.connect()` |
| Desconectar | `EbinexClient.disconnect()` |
| Listar ativos | `get_assets("OPTION")` |
| Consultar payout | `get_payout(asset)` |
| Verificar mercado | `is_market_open(asset)` |
| Histórico | `get_candles_history(...)` |
| Enviar ordem | `buy(asset, direction, stake, duration=60)` |
| Aguardar resultado | `check_win(trade_id, duration=60)` |
| Consultar ordem | `get_trade(trade_id)` |

## Regras para evitar dados futuros

Os artefatos devem provar que não houve lookahead. Para isso, cada sinal deve registrar:

- `decisionTime`;
- `currentCandleOpen`;
- `visibleUntil`;
- `orderDeadline`;
- `effectiveEntryCandle`;
- `expiryCandle`.

Regras:

- estratégia nunca recebe o candle atual;
- estratégia nunca recebe `C[n+1]`;
- indicadores devem ser calculados apenas sobre histórico fechado;
- features com `shift(-1)`, janelas centradas ou normalização global devem ser proibidas;
- o run deve registrar bloqueios por suspeita de lookahead;
- backtest e live devem compartilhar o mesmo contrato temporal.

## Modelo de eventos do run

```text
SessionStarted
CandleClosed(C[n-1])
DecisionWindowOpened(C[n])
SignalGenerated
EntryPreflightPassed ou EntryPreflightRejected
OrderScheduled(C[n+1])
OrderSent
OrderAccepted ou OrderRejected
OperationOpened(C[n+1].open)
OperationSettled(C[n+1].close)
RiskUpdated
SessionStopped, se aplicável
RunClosed
```

## Promoção

Um experimento ou run pode ser promovido quando seus resultados forem considerados referência.

O agente pode promover automaticamente um run quando a meta objetiva de `experiment.yml` for atingida.

Destino:

```text
forge/promoted/<experimento>/
  promotion.yml
  runs/<run-id>/
```

`promotion.yml` deve registrar:

- origem;
- run promovido;
- motivo;
- data;
- métricas principais;
- responsável;
- restrições conhecidas.

## Imutabilidade de runs

Após `RunClosed`, os arquivos dentro de `runs/<run-id>/` não devem ser sobrescritos.

Correções devem gerar:

- novo `run-id`;
- novo experimento;
- ou artefato externo de auditoria que não altere o run original.

## Arquivamento

Experimentos encerrados devem ir para:

```text
forge/archived/YYYY-MM-DD-<experimento>/
```

`archive.yml` deve registrar:

- origem;
- data;
- motivo;
- runs incluídos;
- status final;
- observações.

## Pontos de extensão futura

- Novos schemas de artefatos.
- Novos tipos de run: `backtest`, `simulate`, `live`, `discovery`, `compare`.
- Promoção automática por critérios mínimos.
- Arquivamento automático de experimentos antigos.
- Exportação de runs para dashboards externos.
- Verificação de reprodutibilidade por hash de config e histórico.
