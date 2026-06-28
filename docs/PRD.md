# PRD - Forge, Laboratório de Experimentos Ebinex

## Visão geral

O `forge` é a pasta raiz de artefatos do laboratório de robôs Xenibe/Ebinex. Ela não deve ser tratada como pacote Python nem como local de implementação da lógica.

A lógica de estratégia, provider, backtest, risco e CLI deve viver fora de `forge`. A pasta `forge/` deve guardar apenas experimentos, execuções, configurações congeladas, métricas, relatórios, promoções e arquivos arquivados, em um padrão semelhante ao papel operacional de `/root/dev/xenibe/openspec`.

O código-fonte deve ficar em `/root/dev/xenibe/src`, organizado por feature:

- `src/forge`: aplicação operacional do laboratório, CLI e comandos que leem e gravam artefatos em `forge/`;
- `src/xenibe`: núcleo do domínio Xenibe, como backtest, providers, risco, estratégias, candles e execução.

Arquivos Python com nomes compostos devem ser evitados. Em vez de `risk_manager.py` ou `backtest_engine.py`, a organização deve usar pastas por feature e nomes simples, como `risk/manager.py` e `backtest/engine.py`.

## Objetivo do laboratório

O laboratório deve permitir criar e auditar experimentos de robôs de opções binárias com fidelidade ao funcionamento real da Ebinex, principalmente em M1.

Um experimento é um estudo histórico de busca massiva. Ele deve testar muitos `candidates`, formados por componentes de análise price action, indicadores, filtros, gatilhos, decisão, contextos de mercado, padrões de vela, padrões de mercado e parâmetros, buscando alcançar a meta declarada em `experiment.yml`.

Cada experimento deve ter um nome descritivo e conter seus próprios artefatos:

```text
forge/<nome-descritivo-do-experimento>/
  experiment.yml
  ingest.yml
  searchscope.yml
  runs/<run-id>/
    manifest.json
    config-snapshot.yml
    candidates.jsonl
    scoreboard.json
    rounds.jsonl
    reflections.jsonl
    metrics.json
    report.md
```

### Papéis dos YAMLs principais

- `experiment.yml`: objetivo, hipótese, métrica única de meta, critério de parada e identidade do experimento.
- `ingest.yml`: ativo, timeframe, início, fim, provider, fonte e validação dos dados históricos.
- `searchscope.yml`: espaço de busca, componentes de análise price action, indicadores, filtros, gatilhos, decisão, padrões, contexto de mercado e ranges de parâmetros.
- `risk.yml`: banca, Stop Loss, Stop Win, stake, Soros e Martingale.
- `provider.yml`: parâmetros do provider externo.
- `report.yml`: formato e destino dos relatórios.

## Busca massiva guiada por IA

O `forge` deve permitir que um agente IA conduza a busca massiva de forma autônoma.

Regras:

- o agente pode decidir dinamicamente os limites da busca;
- antes de executar, os limites resolvidos devem ser gravados no run;
- a busca deve parar quando o primeiro `candidate` atingir a meta definida em `experiment.yml`;
- a meta deve ser uma métrica única, objetiva, mensurável e verificável;
- o `scoreboard.json` deve funcionar como campeonato amplo do run;
- o scoreboard deve ranquear candidates e componentes de análise price action;
- candidates devem ser executados em batches;
- após cada batch deve existir um reflection point obrigatório;
- cada reflection point deve atualizar `manifest.json` e registrar decisão em `reflections.jsonl`;
- o sistema deve persistir detalhes completos apenas quando necessário para `approved`, `winner`, debug ou auditoria explícita;
- todo comando JSON deve retornar `nextActions` para orientar o próximo passo do agente.

Exemplos de limites resolvidos:

```json
{
  "resolvedLimits": {
    "maxCombinations": 50000,
    "maxRuntime": "6h",
    "stopOnFirstTarget": true
  }
}
```

## Problema que o sistema resolve

Backtests comuns podem gerar resultados irreais por:

- uso acidental de candles futuros;
- uso do fechamento da vela atual para decidir uma entrada enviada dentro dela;
- simulação de entrada na mesma vela do sinal;
- ignorar bloqueios reais da corretora;
- ignorar payout, ativo fechado, latência e rejeição de ordem;
- tratar opções binárias como compra e venda tradicional de ativo;
- não preservar artefatos suficientes para auditoria posterior.

O `forge` resolve a parte de organização e auditoria: cada execução passa a ter artefatos versionáveis, comparáveis, promovíveis e arquiváveis.

## Funcionamento real da Ebinex M1

Para uma vela M1 aberta às `12:00`:

- o robô só pode analisar dados até `11:59:59`;
- o sinal é decidido no início da vela `12:00`;
- a ordem é enviada durante a vela `12:00`;
- a ordem deve ser enviada antes dos últimos 5 segundos;
- a operação passa a valer na vela `12:01`;
- o resultado é definido no fechamento da vela `12:01`.

## Regras obrigatórias de operação

- Nunca usar dados futuros.
- Nunca usar fechamento da vela atual para decidir entrada enviada dentro dela.
- Nunca considerar que uma operação M1 entra na mesma vela em que o sinal foi enviado.
- Sempre validar payout mínimo.
- Sempre validar se o ativo está aberto.
- Sempre validar se há tempo suficiente antes do bloqueio dos últimos 5 segundos.
- Sempre respeitar Stop Loss e Stop Win da sessão.
- Sempre resetar Soros após loss.
- Nunca ultrapassar o Stop Loss configurado.
- Sempre registrar sinais, rejeições, ordens, resultados e métricas no `run-id` correspondente.
- Nunca alterar um run concluído.

## Backtest sem lookahead bias

O backtest deve iterar candles com fases explícitas:

```text
C[n-1] fechado -> histórico disponível
C[n] atual     -> decisão e envio da ordem
C[n+1] próxima -> entrada efetiva e expiração
```

Para cada índice `n`:

1. Disponibilizar à estratégia apenas candles fechados até `C[n-1]`.
2. Gerar sinal para possível ordem durante `C[n]`.
3. Validar janela de envio antes de `close(C[n]) - 5s`.
4. Validar payout, ativo, saldo e risco.
5. Agendar operação para `C[n+1]`.
6. Calcular resultado usando abertura e fechamento de `C[n+1]`.
7. Persistir o evento e o resultado em `forge/<experimento>/runs/<run-id>/`.

Resultado M1:

- `CALL`: win se `close(C[n+1]) > open(C[n+1])`.
- `PUT`: win se `close(C[n+1]) < open(C[n+1])`.
- empate deve usar `refund` por padrão até confirmação da regra real da Ebinex.

## Gestão de risco

Parâmetros padrão:

```text
Stop Loss = 10% da banca inicial
Stop Win  = 20% da banca inicial
Stake base = Stop Loss / divisor
```

Exemplo:

```text
Banca inicial = 1000
Stop Loss = 100
Stop Win = 200
Divisor = 4
Stake base = 25
```

Bloquear novas entradas quando:

- Stop Loss for atingido;
- Stop Win for atingido;
- payout estiver abaixo do mínimo;
- ativo estiver fechado;
- não houver tempo suficiente para envio;
- stake calculado for maior que risco restante;
- saldo disponível for insuficiente;
- houver ordem pendente que impeça novo ciclo.

Todo bloqueio relevante deve aparecer no resumo do candidate, no scoreboard ou nos detalhes completos quando o candidate for `approved`, `winner`, debug ou auditoria explícita.

## Soros

Soros será a gestão principal.

Regra Soros N1:

1. Primeira entrada usa `stake-base`.
2. Se houver win, próxima entrada usa `stake-base + lucro-anterior`.
3. Se houver novo win, encerra o ciclo.
4. Se houver loss em qualquer etapa, reseta o ciclo.
5. Após reset, a próxima entrada usa `stake-base`.

Regras obrigatórias:

- loss sempre reseta Soros;
- ciclo encerrado volta para `stake-base`;
- stake Soros nunca pode ultrapassar risco restante;
- se stake Soros ultrapassar limite de risco, a entrada deve ser bloqueada.

## Martingale

Martingale deve ser opcional e desativado por padrão.

O sistema deve suportar:

- stake fixa;
- Soros por níveis;
- Martingale;
- combinação controlada entre Soros e Martingale.

Regras:

- Martingale só pode ser usado se configurado;
- Martingale deve ter nível máximo;
- stake Martingale deve respeitar risco restante;
- se stake necessária ultrapassar Stop Loss, bloquear entrada;
- nunca aplicar Martingale de forma implícita.

## Estrutura esperada do `forge`

O `forge` deve ser um repositório local de artefatos, não uma árvore de código Python.

```text
forge/
  config.yml
  promoted/
    <experimento>/
      promotion.yml
      runs/<run-id>/
  archived/
    YYYY-MM-DD-<experimento>/
  <nome-descritivo-do-experimento>/
    experiment.yml
    ingest.yml
    searchscope.yml
    risk.yml
    provider.yml
    report.yml
    runs/
      <run-id>/
        manifest.json
        config-snapshot.yml
        inputs.json
        candidates.jsonl
        scoreboard.json
        rounds.jsonl
        reflections.jsonl
        metrics.json
        report.md
```

## Escopo inicial

- Definir estrutura de artefatos `forge/`.
- Definir organização de código em `src/forge` e `src/xenibe`.
- Organizar por feature, não por camadas genéricas soltas.
- Evitar `_` em nomes compostos de arquivos Python.
- Definir formato de `experiment.yml`, `ingest.yml`, `searchscope.yml` e `runs/<run-id>/`.
- Definir fluxo de promoção e arquivamento.
- Definir contratos esperados nos artefatos JSON/YAML/JSONL.
- Registrar backtests, simulações, métricas, rankings e motivos de rejeição de forma auditável.
- Referenciar provider `pyebinex` por configuração, sem código dentro de `forge`.
- Referenciar estratégias por nome, módulo externo ou identificador, sem implementar código dentro de `forge`.

## Fora de escopo inicial

- Criar código Python dentro de `forge/`.
- Tratar `forge/` como pacote instalável.
- Execução real automática em conta real.
- Interface web.
- Otimização avançada com machine learning.
- Operações multi-broker em produção.
- Garantia de lucro.
- Bypass de bloqueios da corretora.
- Qualquer uso de dados não disponíveis no momento real da decisão.

## Critérios de sucesso

- `forge/` contém apenas artefatos, configurações, runs, promoções e arquivados.
- Cada experimento tem nome descritivo e `experiment.yml`.
- Cada execução tem `runs/<run-id>/` com snapshots e resultados auditáveis.
- Runs concluídos são imutáveis.
- O primeiro `candidate` que atingir a meta encerra a busca.
- Runs que atingirem a meta podem ser promovidos automaticamente pela IA.
- Backtest M1 não usa candle atual nem futuro na decisão.
- Entrada simulada acontece somente na próxima vela.
- Resultado simulado é calculado no fechamento da próxima vela.
- Relatórios mostram métricas, ranking, winner, candidates relevantes, motivos de rejeição e configuração usada.
- Gestão bloqueia entradas ao atingir Stop Loss ou Stop Win.
- Soros reseta corretamente após loss.
- Martingale não opera se desativado.

## Riscos técnicos

- Timestamp dos candles pode ter semântica diferente entre REST, WebSocket e UI.
- Payout pode mudar entre decisão e envio.
- Ativo pode fechar durante a vela.
- Latência pode causar rejeição nos últimos segundos.
- `pyebinex` é não oficial e baseado em engenharia reversa.
- Resultado de empate precisa ser confirmado.
- Histórico pode ter gaps ou candles incompletos.
- Estratégias podem introduzir lookahead por indicadores mal implementados.
- Artefatos incompletos podem impedir auditoria e reprodução de runs.

## Próximos passos

1. Ajustar a documentação para tratar `forge/` como pasta de artefatos.
2. Definir schema de `experiment.yml`, `ingest.yml` e `searchscope.yml`.
3. Definir schema de `manifest.json`, `scoreboard.json`, `metrics.json`, `candidates.jsonl`, `rounds.jsonl` e `reflections.jsonl`.
4. Confirmar regra real de empate na Ebinex.
5. Confirmar preço oficial usado como entrada na operação M1.
6. Implementar a lógica em `src/forge` e `src/xenibe`.
7. Fazer o CLI criar e atualizar apenas artefatos dentro de `forge/`.
