# ADRs - Forge

## ADR 001 - `forge` raiz é pasta de artefatos

### Status

Aceita.

### Contexto

O projeto precisa separar claramente a lógica Python dos artefatos gerados pelo laboratório. A pasta `/root/dev/xenibe/forge` já representa o espaço operacional de experimentos, de forma parecida com `/root/dev/xenibe/openspec`.

### Decisão

`/root/dev/xenibe/forge` será somente uma pasta de artefatos.

Ela pode conter:

- experimentos;
- arquivos YAML declarativos;
- runs;
- JSON, YAML, JSONL e relatórios;
- experimentos promovidos;
- experimentos arquivados.

Ela não deve conter lógica Python.

### Consequências

- Código fica em `/root/dev/xenibe/src`.
- Runs ficam auditáveis e separados do código.
- O CLI deve ler e escrever artefatos em `forge/`, não implementar lógica lá.

## ADR 002 - Código organizado em `src/forge` e `src/xenibe`

### Status

Aceita.

### Contexto

O sistema precisa de uma camada de aplicação para orquestrar o laboratório e uma camada de domínio para backtest, providers, risco e estratégias.

### Decisão

O código será dividido assim:

```text
src/
  forge/
  xenibe/
```

`src/forge` conterá somente CLI e orquestração de artefatos.

`src/xenibe` conterá o núcleo de domínio:

- backtest;
- candles;
- providers;
- risco;
- estratégias;
- execução;
- métricas.

### Consequências

- O CLI não vira domínio.
- O domínio não depende da estrutura física de `forge/`.
- Fica possível reutilizar `src/xenibe` fora do laboratório.

## ADR 003 - Experimento é um estudo histórico de busca massiva

### Status

Aceita.

### Contexto

Um experimento não é apenas um robô configurado. Ele representa um estudo do histórico do gráfico, usando backtest adaptado ao funcionamento real da Ebinex.

### Decisão

Um experimento é uma hipótese de busca sobre histórico, com:

- dados de entrada definidos em `ingest.yml`;
- escopo de busca definido em `searchscope.yml`;
- objetivo definido em `experiment.yml`;
- runs gerados em `runs/<run-id>/`.

O experimento pode testar dezenas de milhares de possibilidades, usando indicadores, contexto de mercado, padrões de vela, padrões de mercado e outras ferramentas configuradas.

### Consequências

- `experiment.yml` define objetivo e critério de parada.
- `ingest.yml` não deve conter regras de busca.
- `searchscope.yml` não deve conter configuração de coleta de dados.
- Runs devem guardar evidências suficientes para reprodutibilidade.

## ADR 004 - Configuração por vários YAMLs por assunto

### Status

Aceita.

### Contexto

Um `config.yml` único simplifica o começo, mas tende a virar um arquivo grande e ambíguo. O laboratório precisa separar responsabilidades.

### Decisão

Usar vários YAMLs por assunto.

Arquivos principais:

```text
experiment.yml
ingest.yml
searchscope.yml
risk.yml
provider.yml
report.yml
```

### Consequências

- Cada arquivo tem uma responsabilidade clara.
- Agentes IA podem editar uma área sem tocar em tudo.
- Snapshots completos continuam sendo gravados dentro de cada run.

## ADR 005 - Nomes compostos usam `-`, não `_`

### Status

Aceita.

### Contexto

O projeto quer uma organização limpa e evitar `_` em nomes compostos de arquivos e pastas.

### Decisão

Usar `kebab-case` para nomes compostos de arquivos, pastas, chaves YAML e IDs operacionais.

Usar `camelCase` em campos JSON retornados pelo CLI, para evitar `_` e manter compatibilidade comum com APIs.

Exemplos:

```text
searchscope.yml
price-action-study/
bt-20260628-120000/
config-snapshot.yml
```

Nomes internos em Python podem seguir a linguagem quando necessário, mas arquivos, pastas e chaves de configuração do projeto devem evitar `_`.

### Consequências

- Estrutura fica mais uniforme.
- IDs de runs ficam legíveis.
- Evita mistura entre `snake_case`, `kebab-case` e nomes soltos.

## ADR 006 - Todo output JSON do CLI deve conter `nextActions`

### Status

Aceita.

### Contexto

A orquestração do `forge` deve ser 100% amigável para agentes IA. O agente precisa saber o próximo passo sem depender de texto livre.

### Decisão

Todo comando com saída JSON deve retornar `nextActions`.

Exemplo:

```json
{
  "status": [{"severity": "info", "code": "run-created", "message": "Run criado"}],
  "data": {"runId": "bt-20260628-120000"},
  "nextActions": [
    {"command": "forge run show robo-lksjdlkkl bt-20260628-120000 --json"},
    {"command": "forge report generate robo-lksjdlkkl bt-20260628-120000 --json"}
  ]
}
```

### Consequências

- O CLI vira um contrato de automação para agentes.
- Fluxos longos podem ser executados autonomamente.
- Erros também devem retornar próximos passos de correção.

## ADR 007 - Limites de busca podem ser decididos dinamicamente pelo agente

### Status

Aceita.

### Contexto

O espaço de busca pode testar dezenas de milhares de combinações. Fixar sempre os mesmos limites pode reduzir a capacidade de exploração do agente.

### Decisão

O agente pode decidir dinamicamente limites de busca, como tempo, combinações, profundidade, filtros e priorização.

Antes de executar, os limites resolvidos devem ser gravados no run.

Campos mínimos:

```json
{
  "resolvedLimits": {
    "maxCombinations": 50000,
    "maxRuntime": "6h",
    "stopOnFirstTarget": true
  }
}
```

### Consequências

- O agente mantém autonomia.
- O run continua auditável.
- A busca não pode começar sem registrar os limites resolvidos.

## ADR 008 - A busca para na primeira meta atingida

### Status

Aceita.

### Contexto

O objetivo do experimento é atingir a meta declarada em `experiment.yml`, não necessariamente encontrar o ótimo global.

### Decisão

Quando uma combinação alcançar a meta objetiva definida em `experiment.yml`, o run deve parar.

### Consequências

- Reduz custo computacional.
- A meta precisa ser objetiva e verificável.
- Se o usuário quiser buscar o melhor resultado, deve criar outro experimento ou alterar a meta.

## ADR 009 - Runs concluídos são imutáveis

### Status

Aceita.

### Contexto

Runs precisam ser auditáveis e reprodutíveis. Alterar um run depois de concluído enfraquece a confiança nos resultados.

### Decisão

Um run concluído nunca deve ser alterado.

Correções devem gerar:

- novo run; ou
- novo experimento; ou
- artefato separado de auditoria, sem sobrescrever o run original.

### Consequências

- Relatórios ficam confiáveis.
- O CLI deve bloquear escrita em run concluído.
- Comandos de correção devem criar novo `run-id`.

## ADR 010 - Promoção pode ser autônoma

### Status

Aceita.

### Contexto

O fluxo do Forge deve ser orquestrado por IA. Se a meta for objetiva, a promoção pode ser uma continuação natural do run.

### Decisão

O agente IA pode promover automaticamente um run quando os critérios de `experiment.yml` forem atingidos.

O arquivamento automático não fica aprovado por esta ADR.

### Consequências

- `nextActions` pode incluir `forge promote run ...`.
- O comando de promoção deve gravar `promotion.yml`.
- A promoção automática deve registrar motivo, métricas e critérios cumpridos.

## ADR 011 - Todo backtest ou simulação testada é `candidate`

### Status

Aceita.

### Contexto

O experimento pode testar dezenas de milhares de backtests ou simulações. Sem uma entidade própria, não há como auditar qual estratégia completa, componentes e parâmetros geraram cada resultado.

### Decisão

Cada backtest ou simulação individual testada dentro de um run deve ser registrada como `candidate`.

Artefato esperado:

```text
runs/<run-id>/candidates.jsonl
```

Cada `candidate` deve registrar a estratégia completa testada, componentes usados, parâmetros, métricas parciais, classificação, status e motivo de aceitação ou rejeição.

Um `candidate` pode ser bom ou ruim. A diferença deve estar nos campos de classificação e métricas, não no nome da entidade.

Classificações permitidas:

- `rejected`: candidate reprovado;
- `approved`: candidate com resultado bom o suficiente para melhoria ou análise;
- `winner`: candidate vencedor do run.

### Consequências

- A busca fica auditável.
- O agente consegue comparar tentativas.
- O primeiro `candidate` que atingir a meta encerra o run.

## ADR 012 - `searchscope.yml` define componentes de análise price action

### Status

Aceita.

### Contexto

O termo “tools” foi usado inicialmente de forma ampla. No domínio do Forge, ele representa tudo que compõe uma análise price action.

### Decisão

`searchscope.yml` deve definir componentes de análise, incluindo:

- indicadores;
- filtros;
- gatilhos;
- decisão;
- configurações;
- padrões de vela;
- padrões de mercado;
- contexto de mercado.

### Consequências

- O termo genérico `tools` deve ser evitado nos schemas principais.
- O schema deve usar `components`.
- Cada componente precisa ter tipo, parâmetros e papel na decisão.

## ADR 013 - Meta do experimento é métrica única

### Status

Aceita.

### Contexto

Metas compostas dificultam a orquestração inicial do agente. O usuário optou por métrica única.

### Decisão

`experiment.yml` deve definir uma métrica principal única para parada do experimento.

Exemplo:

```yaml
target:
  metric: net-pnl
  operator: \">=\"
  value: 200
```

### Consequências

- O agente sabe exatamente quando parar.
- Métricas secundárias podem existir no relatório, mas não controlam a parada.
- Se múltiplas restrições forem necessárias, devem virar outro experimento ou evolução futura.

## ADR 014 - Empate M1 usa `refund` por padrão

### Status

Aceita.

### Contexto

A regra real de empate da Ebinex ainda precisa ser confirmada, mas o laboratório precisa de uma política padrão para backtest.

### Decisão

Até confirmação em produção, empate M1 será tratado como `refund`.

### Consequências

- Empate não soma lucro nem prejuízo.
- A política deve aparecer em `experiment.yml` ou snapshot do run.
- Se a regra real da Ebinex for diferente, todos os backtests afetados devem ser reexecutados.

## ADR 015 - Candidates aprovados são refinados no mesmo run

### Status

Aceita.

### Contexto

Candidates podem ser reprovados, aprovados ou vencedores. Um candidate aprovado ainda pode ser melhorado antes de virar vencedor.

### Decisão

Um `candidate` com classificação `approved` deve alimentar novas rodadas de melhoria dentro do mesmo run.

### Consequências

- Um run pode conter múltiplas rodadas internas.
- `candidates.jsonl` precisa registrar a rodada ou geração do candidate.
- O agente pode continuar refinando enquanto não houver `winner` e enquanto os limites resolvidos permitirem.
- A imutabilidade só vale após o run ser concluído.

## ADR 016 - Reflection point obrigatório após cada batch

### Status

Aceita.

### Contexto

O Forge deve buscar a estratégia ideal de forma agentica, mas sem virar um loop infinito invisível. A análise de padrões de LangGraph/LangChain aponta para execução com estado persistido, checkpoints, interrupções/reflexões e retomada. A análise do OpenSpec aponta para fluxo guiado por `status`, instruções, artefatos e JSON estruturado.

### Decisão

Todo run de busca deve executar candidates em batches. Após cada batch, o run deve entrar em um reflection point obrigatório.

Nesse ponto, o agente deve:

- analisar o scoreboard atual;
- registrar uma decisão em `reflections.jsonl`;
- atualizar `state.json`;
- decidir a próxima ação.

Ações possíveis:

- `continue-search`;
- `refine-approved`;
- `expand-searchscope`;
- `narrow-searchscope`;
- `promote-winner`;
- `stop-without-winner`;
- `request-human-review`, para uso futuro.

### Consequências

- O tamanho do batch pode ser decidido dinamicamente pelo agente.
- Cada decisão agentica fica auditável.
- O run pode ser pausado e retomado a partir de `state.json`.
- `nextActions` do CLI deve orientar o agente a continuar, refletir, promover ou diagnosticar.
