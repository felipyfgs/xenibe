# Xenibe

Repositorio local para organizar o projeto Xenibe e arquivos versionaveis.

## Estado Atual

- Repositorio Git inicializado.
- Arquivos sensiveis ignorados por padrao.
- A instalacao do CLIProxyAPI esta separada em `/root/dev/CLIProxyAPI`.

## GitHub

Para conectar ao GitHub:

```bash
git remote add origin https://github.com/SEU_USUARIO/xenibe.git
git branch -M main
git push -u origin main
```

Antes do push, confirme que nenhum segredo entrou no commit:

```bash
git status --short
git ls-files
```
