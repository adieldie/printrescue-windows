## O que mudou

## Problema resolvido

## Como foi testado

- [ ] `python -m compileall -q .`
- [ ] `python -m unittest discover -s tests -v`
- [ ] Testado em Windows
- [ ] Dados de capturas e logs foram anonimizados

## Risco e rollback

## Checklist de segurança

- [ ] Não habilita SMB1
- [ ] Não armazena senha em arquivo
- [ ] Não remove recursos fora do perfil atual
- [ ] Cria backup antes de mudanças moderadas
