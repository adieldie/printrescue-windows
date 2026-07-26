# PrintRescue Windows

Aplicativo desktop para diagnosticar e reparar problemas de impressoras
compartilhadas no Windows.

O projeto surgiu da necessidade de substituir tentativas manuais repetitivas por
um fluxo verificável: coletar evidências, identificar a camada da falha, criar
backup, aplicar correções controladas e validar o resultado.

## Recursos

- detecção automática do papel do computador: servidor ou cliente;
- diagnóstico de Spooler, SMB, RPC, firewall, rede e resolução de nomes;
- gerenciamento de credenciais pelo Gerenciador de Credenciais do Windows;
- detecção de drivers e importação de pacotes `.INF`;
- configuração de compartilhamento e permissões da fila;
- tentativa de instalação por PrintUI, `Add-Printer` e WScript;
- fallback LPD/LPR quando o Point and Print é bloqueado;
- remoção direcionada de filas conflitantes;
- backup e restauração das chaves de registro alteradas;
- perfis reutilizáveis para diferentes ambientes;
- exportação de relatório em JSON;
- interface em português, sem dependências externas em tempo de execução.

## Requisitos

- Windows 10 ou Windows 11;
- privilégios de administrador para reparos;
- Python 3.10 ou superior para executar pelo código-fonte;
- PyInstaller somente para gerar o executável.

## Execução pelo código-fonte

```bat
RUN_AS_ADMIN.bat
```

Ou, em um terminal elevado:

```powershell
python main.py
```

## Gerar o executável

```bat
BUILD_EXE.bat
```

O arquivo será criado em:

```text
dist\PrintRescue_Windows.exe
```

O executável gerado solicita elevação de administrador por manifesto.

## Primeiros passos

1. Abra a aba **Perfis**.
2. Substitua os valores de exemplo pelos dados da sua rede.
3. No servidor, selecione a impressora física e execute
   **Reparo automático seguro**.
4. No cliente, execute **Verificar tudo**.
5. Use **Reparo automático seguro**.
6. Se o Point and Print continuar bloqueado, use **Recriar fila do zero**.

## Segurança

O PrintRescue não habilita SMB1, não libera acesso de convidado e não desativa
automaticamente as proteções do Point and Print.

As regras de firewall criadas são limitadas ao perfil de rede privada e à
sub-rede local. Alterações relevantes são precedidas por backup.

Consulte [SECURITY.md](SECURITY.md) e
[docs/PRIVACY.md](docs/PRIVACY.md) antes de publicar relatórios.

## Limitações

O projeto não promete corrigir qualquer erro do Windows. Ele automatiza a
investigação e oferece correções para cenários conhecidos de impressão em rede.
Drivers defeituosos, políticas de domínio, edições específicas do Windows e
problemas físicos ainda podem exigir análise manual.

## Estrutura

```text
printrescue/             código principal
tests/                   testes automatizados
docs/                    arquitetura, privacidade e solução de problemas
.github/                 templates e automações do GitHub
main.py                  ponto de entrada
BUILD_EXE.bat            compilação com PyInstaller
RUN_AS_ADMIN.bat         execução elevada pelo código-fonte
```

## Desenvolvimento

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

Para contribuir, leia [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

Distribuído sob a licença MIT. Consulte [LICENSE](LICENSE).
