# Contribuindo

Obrigado pelo interesse no PrintRescue Windows.

## Antes de começar

- não publique senhas, nomes reais de computadores, IPs internos, nomes de
  usuários, relatórios sem revisão ou capturas com dados da empresa;
- abra uma issue descrevendo o comportamento observado;
- mantenha cada pull request focado em um problema;
- preserve os backups e as confirmações antes de ações destrutivas.

## Ambiente de desenvolvimento

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
```

Para executar:

```powershell
python main.py
```

Para validar:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

## Padrão para novos reparos

Todo reparo deve:

1. ter um diagnóstico que prove a falha;
2. alterar apenas recursos relacionados ao perfil atual;
3. criar backup quando modificar registro ou filas existentes;
4. registrar claramente o que foi alterado;
5. retornar sucesso somente após validação;
6. evitar enfraquecer a segurança do Windows;
7. apresentar uma forma de recuperação.

## Commits

Use mensagens objetivas:

```text
feat: adiciona diagnóstico da porta LPR
fix: evita remover sessões SMB de outros servidores
docs: explica dados presentes nos relatórios
test: cobre serialização de perfis
```

## Pull requests

Inclua:

- problema resolvido;
- evidências antes e depois;
- versão do Windows usada no teste;
- riscos e rollback;
- capturas anonimizadas, quando necessárias.
