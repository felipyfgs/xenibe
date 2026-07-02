# Plano: Refresh Amplo Da Skill `forge-run`

## Objetivo

Atualizar `.kilo/skills/forge-run/SKILL.md` para refletir o comportamento atual do Forge/Xenibe após a migração para a CLI compacta e o novo contrato de promoção via `robot.yml`.

## Contexto Verificado

- A skill já descreve boa parte da CLI compacta (`forge status`, `forge check`, `forge show`, `forge data`, `forge backtest`, `forge compare`, `forge promote`).
- A seção de promoção está desatualizada: o código atual cria `promoted/<robot-id>/robot.yml`, com `robotId`, `robot` e contrato em `metadata`, não `promoted/<experiment>/<run-id>/promotion.yml`.
- `run/service.py` agora registra `execution.maxSecondsEnforced`, `search.timedOut`, `search.elapsedSeconds` e `search.evaluatedCandidateCount`; a skill não deve mais dizer que `limits.max-seconds` é apenas registrado e não aplicado.
- `compare/service.py` ordena por `net-profit` e `win-rate`; `total-trades` é exibido, mas não participa do sort atual.
- Backtests agora incluem métricas adicionais de sessão, bloqueios e Soros quando presentes.
- O provider offline foi removido; erros como `provider-credentials-missing` e `provider-unavailable` devem aparecer no diagnóstico.
- Export atual grava pacote JSON com bundle base64 em `exports/`; archive move o experimento para `archived/`.

## Decisões

- Fazer refresh amplo da skill, não apenas correção pontual da promoção.
- Editar somente `.kilo/skills/forge-run/SKILL.md`.
- Manter a skill em pt-BR, sem emojis, com comandos `forge ... --json`.
- Bump sugerido do front matter: `version: "1.1"`.
- Não alterar código, testes, artefatos gerados nem documentação fora da skill neste plano.

## Tarefas De Implementação

1. Atualizar o front matter da skill para versão `1.1`.
2. Revisar a introdução e o objetivo para deixar explícito que a skill cobre a superfície compacta atual do Forge.
3. Em regras de segurança, manter proteção contra sobrescrita de runs e adicionar que promoção deve ser validada por `forge show`/`forge check` após gerar o robô.
4. Na seção de candles, mencionar que `forge data list`/`forge data download` dependem de provider real ou credenciais Ebinex; não há fallback offline canônico.
5. Em backtest por `search-scope.yml`, incluir campos atuais esperados no retorno:
   - `data.searchState`;
   - `data.search.timedOut`;
   - `data.search.elapsedSeconds`;
   - `data.search.evaluatedCandidateCount`;
   - `data.execution.maxSecondsEnforced`.
6. Em backtest fixo/simples, atualizar checklist para escopos atuais:
   - `limits.max-candidates: 1`;
   - `limits.batch-size: 1`;
   - `limits.max-rounds: 1`;
   - `limits.stagnation-rounds: 1`;
   - um valor por parâmetro;
   - `trigger` e `decision` presentes;
   - triggers direcionais atuais derivam `call`/`put` do cenário, então não documentar `side` fixo;
   - para Ebinex, não sugerir `expiration-candles` como dimensão configurável.
7. Em interpretação de resultado, remover a nota obsoleta de que `limits.max-seconds` é registrado mas não aplicado.
8. Em interpretação de resultado, adicionar métricas opcionais atuais quando existirem:
   - `session-win-rate`;
   - `total-sessions`;
   - `blocked-signals`;
   - `soros-trades`;
   - `soros-net-profit`.
9. Em comparação de runs, corrigir a descrição da ordenação atual para `net-profit` e `win-rate`; mencionar `total-trades` como métrica exibida.
10. Reescrever a seção de promoção:
    - Pré-condições: `forge check <experiment> <run-id>` e `forge show <experiment> <run-id>` bem-sucedidos.
    - Comando: `forge promote <experiment> <run-id> --reason "<motivo>" --root forge --json`.
    - Retorno esperado: `data.robotId`, `data.robot`, `data.metadata.robot`, `data.metadata.source`, `data.metadata.strategy`, `data.metadata.risk`, `data.metadata.execution`, `data.metadata.promotion`.
    - Caminho atual: `promoted/<robot-id>/robot.yml`, onde `robot-id` inicial é `<experiment>--<run-id>`.
    - Métricas ficam em `data.metadata.promotion.metrics`.
    - Score fica em `data.metadata.robot.score` e `data.metadata.robot.score-version`.
    - Remover a observação antiga de que `robot.yml` ainda não existe.
11. Adicionar validação pós-promoção recomendada:
    - `forge show <experiment> <run-id> --root forge --json` deve expor `data.promotionStatus.promoted: true` e `data.promotionStatus.robotId`.
    - `forge check --root forge --json` deve continuar válido; se falhar, resumir issues do catálogo promovido.
12. Atualizar diagnósticos comuns:
    - `provider-credentials-missing`: credenciais Ebinex ausentes ou dependência/provider indisponível.
    - `provider-unavailable`: provider retornou zero candles; histórico não deve ter sido escrito.
    - `invalid-artifact` em promoção: run sem candidate `winner` ou robô promovido já existente.
    - `replace-required`: manter orientação de pedir autorização antes de `--replace`.
13. Atualizar comandos de referência para incluir, se fizer sentido no fluxo:
    - `forge data list --root forge --json`;
    - `forge export <experiment> [run-id] --root forge --json`;
    - `forge archive <experiment> --root forge --json`, deixando claro que archive move o experimento para fora do catálogo ativo.
14. Atualizar a saída esperada do agente para incluir, quando houver:
    - `searchState` e `search.timedOut`;
    - métricas de sessão/Soros;
    - caminho do `robot.yml` após promoção;
    - limitações como payout fixo `0.8` e uso de candles sintéticos.

## Riscos

- A skill é instrução operacional; se ela documentar comportamento futuro em vez do código atual, agentes podem executar comandos errados.
- `robot.yml` pode ser invalidado por chaves não kebab-case em estruturas aninhadas; a skill deve mandar validar após promoção, não assumir sucesso sem `check`.
- `archive` é destrutivo no catálogo ativo por mover o experimento; a skill deve tratá-lo como ação explícita, não como próximo passo automático.
- `--allow-synthetic` continua útil só para smoke test e diagnóstico; a skill deve preservar esse alerta.

## Validação Após Implementação

1. Revisar o diff limitado a `.kilo/skills/forge-run/SKILL.md`.
2. Confirmar que não restam referências a:
   - `data.promotion`;
   - `promoted/<experiment>/<run-id>/promotion.yml` como caminho atual;
   - `robot.yml` como não implementado;
   - `limits.max-seconds` como apenas registrado e não aplicado;
   - comparação ordenando por `total-trades`.
3. Confirmar que os comandos documentados usam a CLI compacta atual.
4. Confirmar que a seção de promoção menciona `data.robotId`, `data.robot` e `promoted/<robot-id>/robot.yml`.
5. Não é necessário rodar a suíte Python para uma alteração textual da skill; se desejado, executar apenas validações não mutantes como leitura do arquivo e inspeção do diff.

## Fora Do Escopo

- Corrigir bugs de código identificados no review.
- Rodar backtests, downloads ou promoções reais.
- Alterar artefatos em `forge/`, `promoted/`, `archived/` ou `experiment/`.
- Atualizar documentação fora de `.kilo/skills/forge-run/SKILL.md`.
