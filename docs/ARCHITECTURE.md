# Arquitetura

## Fluxo principal

```text
Perfil
  ↓
Diagnóstico
  ↓
Classificação da falha
  ↓
Backup
  ↓
Reparo direcionado
  ↓
Validação
  ↓
Relatório
```

## Módulos

- `models.py`: perfis e resultados de diagnóstico;
- `storage.py`: persistência local;
- `runner.py`: execução controlada de PowerShell e processos;
- `win_network.py`: autenticação SMB pela API WNet;
- `diagnostics.py`: verificações sem alteração do sistema;
- `repairs.py`: ações corretivas e rollback;
- `app.py`: interface Tkinter e orquestração.

## Princípios

- diagnóstico antes de reparo;
- alteração mínima;
- backup antes de operações moderadas;
- correções idempotentes sempre que possível;
- nenhuma senha em arquivo;
- nenhuma redução silenciosa de segurança;
- logs suficientes para explicar decisões.

## Fallback LPD/LPR

Quando Point and Print falha apesar de rede, driver e autenticação válidos, o
aplicativo pode habilitar:

- serviço LPD no servidor;
- monitor LPR no cliente;
- porta LPR local;
- fila local usando o driver já instalado.

Esse caminho evita depender da criação tradicional de uma conexão Point and
Print, sem habilitar SMB1.
