# Privacidade e dados locais

O PrintRescue não envia telemetria e não possui serviço de nuvem.

## Dados armazenados

Por padrão, o aplicativo usa:

```text
%APPDATA%\PrintRescue
```

Esse diretório pode conter:

- perfis de impressora;
- configurações da interface;
- backups de chaves do registro;
- inventário de filas no momento do backup;
- logs de diagnóstico.

As senhas não são gravadas nos perfis. Quando o usuário permite persistência,
elas são armazenadas pelo Gerenciador de Credenciais do Windows.

## Relatórios

Relatórios e logs podem revelar:

- nome do computador;
- nome do servidor;
- endereços IP internos;
- nomes de usuários locais;
- nomes de impressoras, drivers e portas;
- estrutura da rede.

Revise e anonimize esses arquivos antes de anexá-los a issues públicas.

## Antes de publicar uma captura

Remova ou oculte:

- nomes de pessoas e empresas;
- nomes reais de computadores;
- IPs internos;
- endereços de e-mail;
- caminhos contendo o nome do usuário;
- credenciais e chaves;
- números de série e identificadores de dispositivos.
