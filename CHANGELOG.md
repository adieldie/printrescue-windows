# Changelog

Todas as mudanças relevantes deste projeto serão documentadas aqui.

O formato segue a ideia de *Keep a Changelog* e o versionamento usa SemVer.

## [1.0.0] - 2026-07-25

### Adicionado

- primeira versão pública e anonimizada;
- diagnóstico de serviços, rede, SMB, RPC e drivers;
- reparos para servidor e cliente;
- fallback LPD/LPR;
- backups de registro;
- gerenciamento de perfis;
- importação de drivers `.INF`;
- exportação de relatórios;
- documentação, testes e automação de CI.

### Segurança

- removidos dados de ambientes reais;
- senhas permanecem no Gerenciador de Credenciais do Windows;
- nenhuma política insegura é habilitada automaticamente.
