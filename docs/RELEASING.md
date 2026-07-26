# Publicação de uma versão

1. Atualize `printrescue/__init__.py`.
2. Atualize `CHANGELOG.md`.
3. Execute os testes.
4. Gere o executável em uma máquina Windows.
5. Teste em uma máquina virtual limpa.
6. Crie uma tag no formato `vX.Y.Z`.
7. Publique o executável e o hash SHA-256 na release.
8. Não publique perfis, logs ou backups do ambiente de teste.

## Comandos

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
BUILD_EXE.bat
Get-FileHash .\dist\PrintRescue_Windows.exe -Algorithm SHA256
```
