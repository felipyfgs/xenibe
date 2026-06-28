# Glossário - Forge

## Artefato

Arquivo gerado ou mantido em `/root/dev/xenibe/forge`, como YAML, JSON, JSONL, relatório ou manifesto.

## Candidate

Backtest ou simulação individual testada dentro de um run. Representa uma estratégia completa concreta de análise price action com componentes, parâmetros, regras de decisão, risco associado e resultado. Um candidate deve ser classificado como `rejected`, `approved` ou `winner`.

## Componente de análise

Parte configurável da análise price action. Pode ser indicador, filtro, gatilho, regra de decisão, padrão de vela, padrão de mercado, contexto ou parâmetro.

## `experiment.yml`

Arquivo principal do experimento. Define identidade, objetivo, hipótese, critério de sucesso, critério de parada e metadados.

## Experimento

Estudo histórico de busca massiva sobre um gráfico. O experimento usa dados, ferramentas e critérios definidos para testar muitas combinações até encontrar ou não uma configuração que alcance o objetivo.

## Limites resolvidos

Limites definidos pelo agente antes de iniciar uma busca, como máximo de combinações, tempo máximo, profundidade e filtros ativos. Mesmo quando escolhidos dinamicamente, devem ser gravados no run.

## Forge raiz

Pasta `/root/dev/xenibe/forge`. Contém apenas artefatos operacionais, experimentos, runs, promovidos e arquivados.

## `ingest.yml`

Arquivo que define a busca de dados históricos. Deve conter ativo, timeframe, início, fim, provider, fonte e regras de validação do histórico.

## Lookahead bias

Erro de backtest em que a estratégia usa dados que não estariam disponíveis no momento real da decisão.

## Meta

Métrica única declarada em `experiment.yml` que define quando a busca deve parar.

## `nextActions`

Campo obrigatório em toda saída JSON do CLI. Lista comandos ou ações sugeridas para que um agente IA consiga continuar o fluxo de forma autônoma.

## Promovido

Experimento ou run considerado bom o suficiente para virar referência operacional. Deve ser registrado em `forge/promoted/`.

## Promoção autônoma

Ação em que o agente promove um run sem confirmação humana quando a meta objetiva de `experiment.yml` é atingida.

## Run

Execução específica de um experimento. Pode ser backtest, simulação, discovery, comparação ou execução real futura. Cada run deve ter `run-id` próprio e artefatos em `runs/<run-id>/`.

## Rodada

Ciclo interno de um run em que candidates são testados, classificados e possivelmente usados para gerar novos candidates melhorados.

## Run imutável

Run concluído que não pode ser alterado. Qualquer correção deve gerar novo run ou artefato separado de auditoria.

## `searchscope.yml`

Arquivo que define o espaço de busca do experimento. Deve conter componentes de análise price action, indicadores, filtros, gatilhos, decisão, padrões de vela, padrões de mercado, contexto de mercado, ranges de parâmetros e limites de exploração.

## Tie policy

Política de tratamento de empate. No Forge, o padrão inicial para M1 é `refund`.

## `src/forge`

Código do CLI e da orquestração de artefatos do laboratório. Não contém domínio de trading.

## `src/xenibe`

Núcleo de domínio do sistema. Contém backtest, risco, candles, providers, estratégias, execução e métricas.

## Stop Loss da sessão

Limite máximo de perda permitido na sessão. Regra padrão: 10% da banca inicial.

## Stop Win da sessão

Meta máxima de ganho da sessão. Regra padrão: 20% da banca inicial.

## YAML por assunto

Decisão de dividir configuração em arquivos como `experiment.yml`, `ingest.yml`, `searchscope.yml`, `risk.yml` e `provider.yml`, em vez de concentrar tudo em um único `config.yml`.
