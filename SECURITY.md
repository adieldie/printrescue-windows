# Política de segurança

## Relatando uma vulnerabilidade

Use o recurso **Private vulnerability reporting** do GitHub, quando habilitado
no repositório. Não publique a vulnerabilidade em uma issue aberta antes de
uma correção estar disponível.

Inclua:

- versão afetada;
- passos mínimos para reproduzir;
- impacto;
- proposta de correção, se houver;
- evidências sem credenciais ou dados pessoais.

## Escopo de segurança

O PrintRescue executa operações administrativas no Windows. Alterações em
firewall, registro, serviços, credenciais e filas de impressão devem permanecer
limitadas ao perfil selecionado.

O projeto não deve:

- habilitar SMB1;
- habilitar login de convidado inseguro;
- armazenar senhas em arquivos de perfil;
- desativar silenciosamente políticas de segurança;
- baixar drivers de fontes não oficiais;
- remover filas, portas ou sessões que não pertençam ao perfil atual.
