# Solução de problemas

## O aplicativo não abre

Execute como administrador. Pelo código-fonte:

```bat
RUN_AS_ADMIN.bat
```

## O servidor não responde

Verifique, nesta ordem:

1. nome ou IP do servidor;
2. perfil de rede privada;
3. porta TCP 445;
4. serviço `LanmanServer`;
5. regras de firewall;
6. resolução de nome.

## A senha é solicitada repetidamente

Pode existir uma sessão SMB antiga com outro usuário. Use
**Testar login no servidor** para limpar somente as sessões relacionadas ao
servidor do perfil e validar a credencial.

## O driver existe, mas a fila não é criada

Quando SMB, RPC e credenciais estão corretos, o bloqueio pode estar no Point
and Print ou em uma fila conflitante. Use **Recriar fila do zero** para tentar o
fallback LPR.

## O fallback LPR não funciona

Confirme:

- LPD habilitado no servidor;
- LPR Port Monitor habilitado no cliente;
- porta TCP 515 acessível;
- nome da fila remota idêntico ao compartilhamento;
- driver instalado no cliente.

## Antes de abrir uma issue

Exporte um relatório e remova os dados descritos em
[PRIVACY.md](PRIVACY.md).
