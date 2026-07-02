---
name: forge-run
description: "Use quando o usuario quiser executar ou diagnosticar fluxos Forge/Xenibe pela CLI compacta: validar, baixar dados, rodar busca/backtest, inspecionar, comparar, promover, exportar ou arquivar."
license: MIT
compatibility: Requer o CLI forge disponivel no repositorio Xenibe.
metadata:
  author: xenibe
  version: "1.1"
---

# Skill: forge-run

Conduza execucoes do Forge no projeto Xenibe usando a superficie compacta atual da CLI e a metodologia canonica de artefatos, validacao, backtest, promocao, exportacao e archive.

## Linguagem

Comunique-se em pt-BR.

## Quando Usar

Use esta skill quando o usuario pedir para:

- rodar uma busca;
- executar `search-scope.yml`;
- rodar backtest;
- rodar uma configuracao fixa/simples;
- validar experimento ou run;
- diagnosticar erro de `forge backtest`;
- baixar ou verificar candles;
- mostrar resultado de run;
- comparar runs;
- promover um run;
- exportar pacote de experimento ou run;
- arquivar um experimento.

## Objetivo

Executar ou orientar o fluxo canonico do Forge com seguranca:

- inspecionar o root de artefatos;
- validar artefatos antes de executar;
- garantir que os candles existem ou explicar alternativas;
- rodar busca/backtest;
- ler e resumir o resultado;
- comparar e promover somente runs validos;
- exportar ou arquivar somente quando essa for uma acao explicita do usuario.

## Regras De Seguranca

- Prefira comandos `forge ... --json`.
- Use `--root forge` quando o usuario nao informar outro root.
- Nunca sobrescreva um run concluido.
- Nunca reutilize um `run-id` que ja esteja `completed`.
- Antes de promover um run, valide e mostre o run.
- Depois de promover, confirme a promocao com `forge show` e valide o catalogo com `forge check`.
- Trate `forge/`, `experiment/`, `runs/`, `promoted/` e `archived/` como artefatos do usuario.
- Nao edite artefatos gerados manualmente salvo pedido explicito.
- Nao exponha segredos, credenciais ou variaveis sensiveis.
- Nao use historico sintetico; backtest e simulate exigem candles reais/configurados e parseaveis.
- Trate `forge archive` como acao destrutiva no catalogo ativo: ele move o experimento para `archived/`.

## Root Padrao

Se o usuario nao informar root, use:

```bash
--root forge
```

## Checklist Canonico De Execucao

Use este checklist para validar que o fluxo foi executado corretamente.

### 1. Entrada

- Identificar o experimento alvo.
- Identificar o root de artefatos; se ausente, usar `forge`.
- Identificar se o usuario quer busca ampla, backtest fixo, simulate, comparacao, promocao, exportacao ou archive.
- Identificar se o experimento ja tem historico configurado ou se sera necessario baixar candles.

### 2. Inspecao Inicial

Rodar:

```bash
forge status --root forge --json
```

Validar no retorno:

- `data.state` nao deve impedir a execucao sem diagnostico;
- `root.exists` indica se o root existe;
- `data.blockedReasons` deve ser explicado se houver bloqueio.

### 3. Validacao Do Experimento

Rodar:

```bash
forge check <experiment> --root forge --json
```

Validar no retorno:

- `status[0].level` deve ser `info` para seguir;
- `data.valid` deve ser `true`;
- se falhar, resumir `data.issues` e nao rodar backtest real antes de reparar.

### 4. Disponibilidade De Candles

Verificar pelo `forge data list`, pelo `forge show` ou pelo erro de backtest se ha historico configurado:

```bash
forge data list --root forge --json
```

```bash
forge show <experiment> --root forge --json
```

O Forge atual depende de historico configurado e parseavel; nao ha fallback sintetico/offline canonico.

Se faltar historico, orientar baixar ou configurar dados reais antes do backtest:

- Baixar dados reais/canonicos com provider disponivel:

```bash
forge data download <asset> --experiment <experiment> --timeframe M1 --from <start> --to <end> --root forge --json
```

### 5. Execucao De Busca Via search-scope.yml

Use quando o usuario quiser procurar candidatos ou testar varias combinacoes.

Rodar:

```bash
forge backtest <experiment> --root forge --json
```

Validar no retorno:

- `status[0].level` deve ser `info`;
- `data.runId` deve existir;
- `data.path` deve apontar para `experiment/<experiment>/runs/<run-id>`;
- `data.searchState` deve indicar o estado final da busca;
- `data.search.timedOut` deve ser reportado quando existir;
- `data.search.elapsedSeconds` deve ser reportado quando existir;
- `data.search.evaluatedCandidateCount` deve ser reportado quando existir;
- `data.execution.maxSecondsEnforced` deve ser reportado quando existir;
- `data.metrics` deve conter metricas;
- `data.limitations` deve ser lido e reportado quando relevante.

### 6. Execucao De Backtest Simples/Fixo

O Forge atual nao possui um comando separado para single-strategy backtest. Para executar uma configuracao fixa, o `search-scope.yml` deve gerar apenas um candidato.

Checklist do `search-scope.yml` fixo:

- `limits.max-candidates: 1`;
- `limits.batch-size: 1`;
- `limits.max-rounds: 1`;
- `limits.stagnation-rounds: 1`;
- cada parametro de componente deve ter apenas um valor;
- `trigger` e `decision` devem existir;
- triggers direcionais atuais derivam `call`/`put` do cenario; nao documente `side` fixo.
- em Ebinex, nao trate `expiration-candles` como dimensao configuravel do escopo.

Depois rode o mesmo comando:

```bash
forge backtest <experiment> --root forge --json
```

Explique que e um backtest fixo porque o escopo gera apenas um candidato.

### 7. Execucao Em Modo simulate

Use quando o usuario pedir simulate explicitamente.

```bash
forge backtest <experiment> --mode simulate --root forge --json
```

Se usar `--run-id`, ele deve iniciar com `sim-`:

```bash
forge backtest <experiment> --mode simulate --run-id sim-YYYYMMDD-HHMMSS --root forge --json
```

Explique que, no estado atual, `simulate` reaproveita o fluxo historico do backtest e se diferencia por `mode=simulate` e prefixo `sim-`.

### 8. Inspecao Do Run Gerado

Depois de uma execucao bem-sucedida, rodar:

```bash
forge show <experiment> <run-id> --root forge --json
```

Validar no retorno:

- `data.metrics` existe;
- `data.manifest.status` e `completed`;
- `data.report` existe;
- `data.artifactPaths` lista os artefatos gravados.

### 9. Validacao Do Run

Rodar:

```bash
forge check <experiment> <run-id> --root forge --json
```

Validar no retorno:

- `data.valid` deve ser `true`;
- se falhar, explicar issues e nao promover o run.

### 10. Interpretacao Do Resultado

Ao resumir um run, destaque:

- `runId`;
- `searchState`;
- `bestCandidate`;
- `metrics.winning-candidate`;
- `metrics.best-candidate`;
- `metrics.win-rate`;
- `metrics.net-profit`;
- `metrics.total-trades`;
- `metrics.session-win-rate`, quando existir;
- `metrics.total-sessions`, quando existir;
- `metrics.blocked-signals`, quando existir;
- `metrics.soros-trades`, quando existir;
- `metrics.soros-net-profit`, quando existir;
- limitacoes relevantes.

Sempre mencionar quando aplicavel:

- payout fixo `0.8` no backtest;
- `execution.maxSecondsEnforced`, quando informado;
- origem do historico em `execution.dataSource`, quando informado;
- resultado com amostra pequena nao deve ser tratado como evidencia robusta.

### 11. Comparacao De Runs

Quando houver dois ou mais runs validos:

```bash
forge compare <experiment> <run-id-a> <run-id-b> --root forge --json
```

Validar no retorno:

- `data.runs` deve conter ranking;
- `data.bestRunId` deve existir quando houver runs validos.

Explique que a comparacao atual ordena principalmente por:

- `net-profit`;
- `win-rate`.

`total-trades` e exibido como metrica de apoio, mas nao participa da ordenacao atual.

### 12. Promocao

Pre-condicoes obrigatorias antes de promover:

```bash
forge check <experiment> <run-id> --root forge --json
forge show <experiment> <run-id> --root forge --json
```

Promover:

```bash
forge promote <experiment> <run-id> --reason "<motivo>" --root forge --json
```

Validar no retorno:

- `data.robotId` deve existir;
- `data.robot` deve existir;
- `data.metadata.robot` deve existir;
- `data.metadata.source` deve conter `experiment` e `run-id`;
- `data.metadata.strategy` deve existir;
- `data.metadata.risk` deve existir;
- `data.metadata.execution` deve existir;
- `data.metadata.promotion` deve existir.

Caminho atual do robo promovido:

```text
promoted/<robot-id>/robot.yml
```

O `robot-id` inicial usa o formato `<experiment>--<run-id>`.

Ao resumir a promocao, destaque:

- metricas em `data.metadata.promotion.metrics`;
- score em `data.metadata.robot.score`;
- versao do score em `data.metadata.robot.score-version`;
- caminho `promoted/<robot-id>/robot.yml`.

Validacao pos-promocao recomendada:

```bash
forge show <experiment> <run-id> --root forge --json
forge check --root forge --json
```

O `forge show` deve expor `data.promotionStatus.promoted: true` e `data.promotionStatus.robotId`.

O `forge check` deve continuar valido. Se falhar, resumir issues do catalogo promovido; a validacao de robo promovido e estrita quanto a chaves kebab-case aninhadas.

## Diagnostico De Erros Comuns

### missing-artifact

Se ocorrer em backtest, provavelmente faltam candles parseaveis.

Acoes:

- sugerir `forge data download` com asset/timeframe/range do `ingest.yml`;
- conferir se `ingest.yml:data.path` aponta para CSV/diretorio com candles parseaveis.

### provider-credentials-missing

Credenciais Ebinex ausentes ou dependencia/provider indisponivel.

Acoes:

- explicar que nao ha fallback offline canonico para candles reais;
- pedir que o usuario configure as credenciais/provider ou forneca historico local parseavel.

### provider-unavailable

O provider retornou zero candles ou falhou antes de gravar historico canonico.

Acoes:

- explicar que o historico nao deve ter sido escrito;
- revisar asset, timeframe e intervalo;
- tentar novamente somente com provider/credenciais disponiveis.

### invalid-artifact

Rodar:

```bash
forge check <experiment> --root forge --json
```

Depois resumir `data.issues` com caminho, codigo e correcao sugerida.

Em promocao, tambem pode indicar run sem candidate `winner` ou robo promovido ja existente.

### immutable-run

O run ja esta completo.

Acoes:

- nao alterar o run existente;
- gerar novo run id omitindo `--run-id`;
- ou informar um novo `bt-YYYYMMDD-HHMMSS`/`sim-YYYYMMDD-HHMMSS` compativel com o modo.

### replace-required

O historico canonico tem cobertura desconectada do intervalo solicitado.

Acoes:

- explicar o intervalo atual e o solicitado;
- usar `--replace` somente se o usuario autorizar substituir a cobertura canonica.

## Comandos De Referencia

Status:

```bash
forge status --root forge --json
```

Validar root:

```bash
forge check --root forge --json
```

Validar experimento:

```bash
forge check <experiment> --root forge --json
```

Mostrar experimento:

```bash
forge show <experiment> --root forge --json
```

Listar candles:

```bash
forge data list --root forge --json
```

Baixar candles:

```bash
forge data download <asset> --experiment <experiment> --timeframe M1 --from <start> --to <end> --root forge --json
```

Rodar busca/backtest:

```bash
forge backtest <experiment> --root forge --json
```

Mostrar run:

```bash
forge show <experiment> <run-id> --root forge --json
```

Validar run:

```bash
forge check <experiment> <run-id> --root forge --json
```

Comparar runs:

```bash
forge compare <experiment> <run-id-a> <run-id-b> --root forge --json
```

Promover run:

```bash
forge promote <experiment> <run-id> --reason "<motivo>" --root forge --json
```

Exportar experimento ou run:

```bash
forge export <experiment> [run-id] --root forge --json
```

O export atual grava um pacote JSON em `exports/` com conteudo de arquivos embutido em base64; o retorno contem metadados e caminho do export, nao o bundle completo.

Arquivar experimento:

```bash
forge archive <experiment> --root forge --json
```

Archive move o experimento para `archived/` e o remove do catalogo ativo. Execute somente quando o usuario pedir explicitamente.

## Saida Esperada Do Agente

Ao finalizar um fluxo, responder com:

- comando executado;
- `runId` quando houver;
- `searchState` e `search.timedOut`, quando houver;
- resumo das metricas principais;
- metricas de sessao, bloqueios e Soros, quando houver;
- validacoes executadas;
- caminho `promoted/<robot-id>/robot.yml`, quando houver promocao;
- limitacoes observadas;
- limitacoes como payout fixo `0.8` e tamanho/qualidade da amostra historica;
- proximas acoes naturais apenas quando forem relevantes.
