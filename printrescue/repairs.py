from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import PrinterProfile
from .runner import (
    RunResult,
    hostname,
    powershell,
    powershell_tempfile,
    ps_quote,
    run,
    tcp_test,
)
from .storage import Storage
from .win_network import connect as wnet_connect
from .win_network import disconnect as wnet_disconnect


class Repairs:
    def __init__(self, storage: Storage, emit: Callable[[str, str], None]) -> None:
        self.storage = storage
        self.emit = emit

    def log(self, text: str, level: str = "info") -> None:
        self.emit(text, level)

    def backup(self, profile: PrinterProfile) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = self.storage.backups / f"{hostname()}_{stamp}"
        folder.mkdir(parents=True, exist_ok=True)

        keys = {
            "printers_rpc.reg": r"HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Printers\RPC",
            "printers_policy.reg": r"HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Printers",
            "point_print.reg": r"HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint",
        }
        for filename, key in keys.items():
            run(["reg.exe", "export", key, str(folder / filename), "/y"], timeout=30)

        info = powershell(
            "Get-Printer -ErrorAction SilentlyContinue | "
            "Select-Object Name,Type,DriverName,PortName,Shared,ShareName | "
            "ConvertTo-Json -Depth 4"
        )
        (folder / "printers.json").write_text(info.stdout or "[]", encoding="utf-8")
        (folder / "profile.json").write_text(
            json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.log(f"Backup criado: {folder}", "ok")
        return folder

    def restore_registry_backup(self, folder: Path) -> bool:
        files = list(folder.glob("*.reg"))
        if not files:
            self.log("Nenhum arquivo .reg encontrado no backup.", "error")
            return False
        ok = True
        for file in files:
            result = run(["reg.exe", "import", str(file)], timeout=45)
            if not result.ok:
                ok = False
                self.log(f"Falha restaurando {file.name}: {result.stderr}", "error")
        powershell("Restart-Service Spooler -Force", timeout=45)
        if ok:
            self.log("Registro restaurado; Spooler reiniciado.", "ok")
        return ok

    def set_private_network(self) -> bool:
        r = powershell(
            "Get-NetConnectionProfile -ErrorAction SilentlyContinue | "
            "Where-Object {$_.NetworkCategory -eq 'Public' -and "
            "$_.IPv4Connectivity -ne 'Disconnected'} | "
            "ForEach-Object {Set-NetConnectionProfile "
            "-InterfaceIndex $_.InterfaceIndex -NetworkCategory Private}"
        )
        self.log(
            "Rede ajustada para Privada." if r.ok else f"Falha na rede: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def services(self, server: bool) -> bool:
        names = ["Spooler", "LanmanWorkstation"]
        if server:
            names.extend(["LanmanServer", "FDResPub", "fdPHost"])
        joined = ",".join(f"'{ps_quote(n)}'" for n in names)
        r = powershell(
            f"$names=@({joined});"
            "foreach($n in $names){"
            "$s=Get-Service -Name $n -ErrorAction SilentlyContinue;"
            "if($s){"
            "Set-Service -Name $n -StartupType Automatic;"
            "$current=Get-Service -Name $n;"
            "if($current.Status -ne 'Running'){Start-Service -Name $n}"
            "}"
            "}"
        )
        self.log(
            "Serviços necessários iniciados." if r.ok else f"Falha em serviços: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def firewall(self, server: bool) -> bool:
        custom = ""
        if server:
            custom = """
            foreach($item in @(
              @{Name='PrintRescue SMB 445';Port=445},
              @{Name='PrintRescue RPC 135';Port=135}
            )){
              $r=Get-NetFirewallRule -DisplayName $item.Name -ErrorAction SilentlyContinue
              if($r){
                Set-NetFirewallRule -DisplayName $item.Name -Enabled True -Profile Private
              }else{
                New-NetFirewallRule -DisplayName $item.Name -Direction Inbound -Action Allow `
                  -Protocol TCP -LocalPort $item.Port -Profile Private `
                  -RemoteAddress LocalSubnet | Out-Null
              }
            }
            """
        r = powershell(
            "Get-NetFirewallRule -ErrorAction SilentlyContinue | "
            "Where-Object {$_.Name -like 'FPS-*'} | "
            "Set-NetFirewallRule -Enabled True -Profile Private "
            "-ErrorAction SilentlyContinue;"
            + custom
        )
        self.log(
            "Firewall de impressão ajustado para a rede privada."
            if r.ok
            else f"Falha no firewall: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def rpc_server(self) -> bool:
        r = powershell(
            "$k='HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\Printers\\RPC';"
            "New-Item -Path $k -Force | Out-Null;"
            "New-ItemProperty -Path $k -Name RpcProtocols -PropertyType DWord "
            "-Value 7 -Force | Out-Null;"
            "Restart-Service Spooler -Force"
        )
        self.log(
            "Servidor habilitado para RPC por TCP e Named Pipes."
            if r.ok
            else f"Falha no RPC do servidor: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def rpc_client(self) -> bool:
        r = powershell(
            "$k='HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\Printers\\RPC';"
            "New-Item -Path $k -Force | Out-Null;"
            "New-ItemProperty -Path $k -Name RpcUseNamedPipeProtocol "
            "-PropertyType DWord -Value 1 -Force | Out-Null;"
            "Restart-Service Spooler -Force"
        )
        self.log(
            "Cliente configurado para RPC over Named Pipes."
            if r.ok
            else f"Falha no RPC do cliente: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def hosts(self, profile: PrinterProfile) -> bool:
        if not profile.server_ip:
            return True
        script = f"""
        $hosts=Join-Path $env:WINDIR 'System32\\drivers\\etc\\hosts'
        $server='{ps_quote(profile.server_name)}'
        $ip='{ps_quote(profile.server_ip)}'
        $escaped=[regex]::Escape($server)
        $lines=@(Get-Content -LiteralPath $hosts -ErrorAction Stop)
        $lines=@($lines | Where-Object {{$_ -notmatch "^\\s*(?!#)\\S+\\s+.*\\b$escaped\\b"}})
        $lines += "$ip`t$server"
        Set-Content -LiteralPath $hosts -Value $lines -Encoding ASCII
        Clear-DnsClientCache -ErrorAction SilentlyContinue
        """
        r = powershell(script)
        self.log(
            f"Nome {profile.server_name} fixado em {profile.server_ip}."
            if r.ok
            else f"Falha no arquivo hosts: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def create_or_update_user(self, profile: PrinterProfile, password: str | None) -> bool:
        exists = powershell(
            f"if(Get-LocalUser -Name '{ps_quote(profile.network_user)}' "
            "-ErrorAction SilentlyContinue){exit 0}else{exit 2}"
        )
        if exists.ok:
            r = powershell(
                f"Enable-LocalUser -Name '{ps_quote(profile.network_user)}' "
                "-ErrorAction SilentlyContinue;"
                f"Set-LocalUser -Name '{ps_quote(profile.network_user)}' "
                "-PasswordNeverExpires $true"
            )
            self.log(
                f"Usuário {profile.network_user} ativado e sem expiração de senha."
                if r.ok else f"Falha ajustando usuário: {r.stderr}",
                "ok" if r.ok else "error",
            )
            return r.ok

        if not password:
            self.log("O usuário não existe e nenhuma senha foi fornecida.", "error")
            return False

        script = f"""
        $line=[Console]::In.ReadLine()
        $sec=ConvertTo-SecureString $line -AsPlainText -Force
        New-LocalUser -Name '{ps_quote(profile.network_user)}' -Password $sec `
          -Description 'Acesso à impressora compartilhada' `
          -AccountNeverExpires -PasswordNeverExpires | Out-Null
        Enable-LocalUser -Name '{ps_quote(profile.network_user)}'
        """
        r = powershell_tempfile(script, input_text=password + "\n")
        self.log(
            f"Usuário {profile.network_user} criado."
            if r.ok else f"Falha criando usuário: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def share_printer(self, profile: PrinterProfile) -> bool:
        r = powershell(
            f"$p=Get-Printer -Name '{ps_quote(profile.local_printer_name)}' "
            "-ErrorAction Stop;"
            f"Set-Printer -Name $p.Name -Shared $true "
            f"-ShareName '{ps_quote(profile.share_name)}';"
            "Restart-Service Spooler -Force"
        )
        self.log(
            rf"Compartilhamento pronto: \\{profile.server_name}\{profile.share_name}"
            if r.ok else f"Falha compartilhando a impressora: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def grant_print_permission(self, profile: PrinterProfile) -> bool:
        name = ps_quote(profile.local_printer_name)
        script = f"""
        $printerName='{name}'
        $wmiName=$printerName.Replace('\\','\\\\').Replace("'","''")
        $p=Get-WmiObject -Class Win32_Printer -Filter "Name='$wmiName'" -ErrorAction Stop
        $p.psbase.Scope.Options.EnablePrivileges=$true
        $r=$p.GetSecurityDescriptor()
        if($r.ReturnValue -ne 0 -or -not $r.Descriptor){{throw "Falha lendo ACL"}}
        $sd=$r.Descriptor
        $dacl=@($sd.DACL)
        $sid=[Security.Principal.SecurityIdentifier]::new('S-1-5-11')
        [byte[]]$bytes=New-Object byte[] $sid.BinaryLength
        $sid.GetBinaryForm($bytes,0)
        $exists=$false
        foreach($item in $dacl){{
          try{{
            if($item.Trustee.SID){{
              $current=[Security.Principal.SecurityIdentifier]::new(
                [byte[]]$item.Trustee.SID,0
              )
              if($current.Value -eq 'S-1-5-11' -and $item.AceType -eq 0 -and
                (($item.AccessMask -band 131080) -eq 131080)){{
                  $exists=$true;break
              }}
            }}
          }}catch{{}}
        }}
        if(-not $exists){{
          $t=([WMIClass]'Win32_Trustee').CreateInstance()
          $t.Name='Authenticated Users'
          $t.SID=$bytes
          $t.SidLength=$sid.BinaryLength
          $a=([WMIClass]'Win32_Ace').CreateInstance()
          $a.AccessMask=131080
          $a.AceType=0
          $a.AceFlags=0
          $a.Trustee=$t
          $sd.DACL=@($dacl+$a)
          $sd.ControlFlags=$sd.ControlFlags -bor 0x0004
          $set=$p.SetSecurityDescriptor($sd)
          if($set.ReturnValue -ne 0){{throw "Falha gravando ACL: $($set.ReturnValue)"}}
        }}
        """
        r = powershell(script, timeout=120)
        self.log(
            "Permissão de impressão concedida a Usuários Autenticados."
            if r.ok else f"Falha nas permissões da fila: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def _server_targets(self, profile: PrinterProfile) -> list[str]:
        targets = [
            rf"\\{profile.server_name}\IPC$",
            rf"\\{profile.server_name}\{profile.share_name}",
        ]
        if profile.server_ip:
            targets.extend(
                [
                    rf"\\{profile.server_ip}\IPC$",
                    rf"\\{profile.server_ip}\{profile.share_name}",
                ]
            )
        # Preserve order while removing duplicates.
        return list(dict.fromkeys(targets))

    def disconnect_server_sessions(
        self,
        profile: PrinterProfile,
        *,
        purge_credentials: bool = False,
    ) -> bool:
        """
        Remove somente sessões ligadas ao servidor deste perfil.

        Não usa `net use * /delete`, pois isso derrubaria compartilhamentos
        de outros servidores do usuário.
        """
        server_names = {
            profile.server_name.casefold(),
            profile.server_ip.casefold() if profile.server_ip else "",
        }
        server_names.discard("")

        self.log(
            "Limpando somente as sessões antigas deste servidor...",
            "info",
        )

        # Remove mapeamentos conhecidos pelo cmdlet SMB.
        script = (
            "$names=@("
            + ",".join(
                f"'{ps_quote(value)}'"
                for value in sorted(server_names)
            )
            + ");"
            "Get-SmbMapping -ErrorAction SilentlyContinue | "
            "Where-Object {"
            "$remote=$_.RemotePath.ToLowerInvariant();"
            "$match=$false;"
            "foreach($n in $names){"
            "if($remote.StartsWith(('\\\\'+$n+'\\').ToLowerInvariant()))"
            "{$match=$true}"
            "};$match"
            "} | ForEach-Object {"
            "Remove-SmbMapping -RemotePath $_.RemotePath "
            "-Force -UpdateProfile -ErrorAction SilentlyContinue"
            "}"
        )
        powershell(script, timeout=45)

        # Remove caminhos exatos pela API oficial WNet.
        for target in self._server_targets(profile):
            wnet_disconnect(target, force=True)

        # O `net use` pode listar conexões ocultas que Get-SmbMapping não mostrou.
        listed = run(["net.exe", "use"], timeout=30)
        if listed.stdout:
            import re

            paths = re.findall(
                r"\\\\[^\s\\]+\\[^\s]+",
                listed.stdout,
                flags=re.IGNORECASE,
            )
            for remote in paths:
                folded = remote.casefold()
                if any(
                    folded.startswith(rf"\\{name}\\")
                    for name in server_names
                ):
                    run(
                        ["net.exe", "use", remote, "/delete", "/y"],
                        timeout=30,
                    )

        if purge_credentials:
            run(
                ["cmdkey.exe", f"/delete:{profile.server_name}"],
                timeout=20,
            )
            if profile.server_ip:
                run(
                    ["cmdkey.exe", f"/delete:{profile.server_ip}"],
                    timeout=20,
                )

        self.log("Sessões conflitantes do servidor foram encerradas.", "ok")
        return True

    def save_credential(self, profile: PrinterProfile, password: str) -> bool:
        """
        Salva a credencial somente depois que a autenticação real foi validada.
        """
        targets = [profile.server_name]
        if profile.server_ip:
            targets.append(profile.server_ip)

        username = f"{profile.server_name}\\{profile.network_user}"
        success = True

        for target in dict.fromkeys(targets):
            run(["cmdkey.exe", f"/delete:{target}"], timeout=20)
            result = run(
                [
                    "cmdkey.exe",
                    f"/add:{target}",
                    f"/user:{username}",
                    f"/pass:{password}",
                ],
                timeout=30,
            )
            if not result.ok:
                success = False
                self.log(
                    f"Não foi possível salvar a credencial para {target}: "
                    f"{result.stderr or result.stdout}",
                    "warn",
                )

        self.log(
            "Credencial validada e salva no Windows."
            if success
            else "A conexão funcionou, mas alguma credencial não pôde ser persistida.",
            "ok" if success else "warn",
        )
        return success

    def authenticate_saved(
        self,
        profile: PrinterProfile,
    ) -> tuple[bool, str, int]:
        """
        Tenta usar a credencial que já está no Windows.
        Não pergunta senha se ela ainda for válida.
        """
        self.disconnect_server_sessions(
            profile,
            purge_credentials=False,
        )

        remote = rf"\\{profile.server_name}\IPC$"
        result = wnet_connect(remote, persistent=False)

        if result.ok:
            self.log(
                "A credencial já salva foi validada; não é necessário digitar a senha.",
                "ok",
            )
            return True, result.message, result.code

        self.log(
            f"A credencial salva não autenticou: {result.message} "
            f"(código {result.code}).",
            "warn",
        )
        return False, result.message, result.code

    def authenticate_with_password(
        self,
        profile: PrinterProfile,
        password: str,
    ) -> tuple[bool, str, int]:
        """
        Autentica pela API de rede do Windows, sem depender de `net use`
        interpretando credenciais antigas.
        """
        self.disconnect_server_sessions(
            profile,
            purge_credentials=True,
        )

        username = f"{profile.server_name}\\{profile.network_user}"
        remote = rf"\\{profile.server_name}\IPC$"

        result = wnet_connect(
            remote,
            username=username,
            password=password,
            persistent=False,
        )

        # Erro 1219: ainda existe alguma sessão conflitante que o Windows
        # não expôs na primeira limpeza. Limpa novamente e tenta uma vez.
        if not result.ok and result.code == 1219:
            self.log(
                "O Windows encontrou outra sessão com credenciais diferentes. "
                "Executando uma segunda limpeza direcionada...",
                "warn",
            )
            self.disconnect_server_sessions(
                profile,
                purge_credentials=True,
            )
            result = wnet_connect(
                remote,
                username=username,
                password=password,
                persistent=False,
            )

        if not result.ok:
            self.log(
                f"Falha ao autenticar em {remote}: {result.message} "
                f"(código {result.code}).",
                "error",
            )
            return False, result.message, result.code

        self.log(
            f"Autenticação confirmada como {username}.",
            "ok",
        )
        self.save_credential(profile, password)
        return True, result.message, result.code

    def remove_old_connection(self, profile: PrinterProfile) -> None:
        """
        Remove filas antigas sem apagar indiscriminadamente outras conexões.
        As sessões SMB são tratadas separadamente pelos métodos de autenticação.
        """
        path = rf"\\{profile.server_name}\{profile.share_name}"
        powershell(
            f"Get-Printer -ErrorAction SilentlyContinue | "
            f"Where-Object {{$_.Name -eq '{ps_quote(path)}' -or "
            f"$_.Name -like '*{ps_quote(profile.share_name)}*'}} | "
            "Remove-Printer -ErrorAction SilentlyContinue"
        )
        self.log("Filas antigas deste perfil foram removidas.", "ok")

    def queue_exists(self, profile: PrinterProfile) -> bool:
        path = rf"\\{profile.server_name}\{profile.share_name}"
        lpr_port = f"LPR_{profile.server_name}_{profile.share_name}"
        r = powershell(
            f"$p=Get-Printer -ErrorAction SilentlyContinue | "
            f"Where-Object {{$_.Name -eq '{ps_quote(path)}' -or "
            f"$_.Name -eq '{ps_quote(profile.client_queue_name)}' -or "
            f"$_.PortName -eq '{ps_quote(lpr_port)}' -or "
            f"($_.Type -eq 'Connection' -and "
            f"$_.Name -like '*{ps_quote(profile.share_name)}*')}};"
            "if($p){exit 0}else{exit 2}"
        )
        return r.ok

    def install_shared_queue(self, profile: PrinterProfile) -> tuple[bool, bool]:
        path = rf"\\{profile.server_name}\{profile.share_name}"
        attempts = [
            (
                "PrintUIEntry",
                lambda: run(
                    [
                        str(Path(os.environ["WINDIR"]) / "System32" / "rundll32.exe"),
                        "printui.dll,PrintUIEntry",
                        "/in",
                        f"/n{path}",
                    ],
                    timeout=90,
                ),
            ),
            (
                "Add-Printer",
                lambda: powershell(
                    f"Add-Printer -ConnectionName '{ps_quote(path)}' "
                    "-ErrorAction Stop",
                    timeout=90,
                ),
            ),
            (
                "WScript.Network",
                lambda: powershell(
                    "$n=New-Object -ComObject WScript.Network;"
                    f"$n.AddWindowsPrinterConnection('{ps_quote(path)}')",
                    timeout=90,
                ),
            ),
        ]

        for label, action in attempts:
            self.log(f"Tentando instalar por {label}...", "info")
            r = action()
            time.sleep(4)
            if self.queue_exists(profile):
                self.log(f"Fila instalada por {label}.", "ok")
                return True, False
            self.log(
                f"{label} não instalou: "
                f"{r.stderr or r.stdout or 'sem confirmação'}",
                "warn",
            )

        self.log(
            "O Windows bloqueou os métodos Point and Print. "
            "Mudando automaticamente para o fallback LPR...",
            "warn",
        )
        if profile.enable_lpr_fallback:
            return self.rebuild_client_queue_lpr(
                profile,
                force_cleanup=True,
            )

        self.log(
            "O fallback LPR está desativado neste perfil.",
            "error",
        )
        return False, False


    def enable_lpd_server(self, profile: PrinterProfile) -> bool:
        """Ativa o serviço LPD no servidor, restrito à rede privada local."""
        self.log("Ativando fallback LPD no servidor...", "info")
        script = """
        $feature=Get-WindowsOptionalFeature -Online `
          -FeatureName Printing-Foundation-LPDPrintService `
          -ErrorAction SilentlyContinue
        if(-not $feature){
          throw 'O recurso LPD Print Service não existe nesta edição do Windows.'
        }
        if($feature.State -ne 'Enabled'){
          $result=Enable-WindowsOptionalFeature -Online `
            -FeatureName Printing-Foundation-LPDPrintService `
            -All -NoRestart -ErrorAction Stop
          if($result.RestartNeeded){Write-Output 'RESTART_NEEDED'}
        }
        $svc=Get-Service -Name LPDSVC -ErrorAction SilentlyContinue
        if($svc){
          Set-Service -Name LPDSVC -StartupType Automatic
          if((Get-Service LPDSVC).Status -ne 'Running'){
            Start-Service LPDSVC
          }
        }
        $rule='PrintRescue LPD 515 - rede privada'
        if(Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue){
          Set-NetFirewallRule -DisplayName $rule -Enabled True -Profile Private
        }else{
          New-NetFirewallRule -DisplayName $rule -Direction Inbound `
            -Action Allow -Protocol TCP -LocalPort 515 -Profile Private `
            -RemoteAddress LocalSubnet | Out-Null
        }
        """
        r = powershell(script, timeout=240)
        if r.ok:
            self.log(
                "Fallback LPD ativo no servidor, limitado à rede local.",
                "ok",
            )
            if "RESTART_NEEDED" in r.stdout:
                self.log(
                    "O Windows informou que uma reinicialização do servidor "
                    "pode ser necessária para concluir o LPD.",
                    "warn",
                )
            return True
        self.log(
            f"Falha ativando LPD no servidor: {r.stderr or r.stdout}",
            "error",
        )
        return False

    def enable_lpr_client(self) -> tuple[bool, bool]:
        """Ativa o monitor LPR. Retorna (sucesso, precisa_reiniciar)."""
        self.log("Ativando o monitor LPR no cliente...", "info")
        script = """
        $feature=Get-WindowsOptionalFeature -Online `
          -FeatureName Printing-Foundation-LPRPortMonitor `
          -ErrorAction SilentlyContinue
        if(-not $feature){
          throw 'O recurso LPR Port Monitor não existe nesta edição do Windows.'
        }
        $restart=$false
        if($feature.State -ne 'Enabled'){
          $result=Enable-WindowsOptionalFeature -Online `
            -FeatureName Printing-Foundation-LPRPortMonitor `
            -All -NoRestart -ErrorAction Stop
          $restart=[bool]$result.RestartNeeded
        }
        [pscustomobject]@{
          Enabled=$true
          RestartNeeded=$restart
        } | ConvertTo-Json -Compress
        """
        r = powershell(script, timeout=240)
        if not r.ok:
            self.log(
                f"Falha ativando LPR no cliente: {r.stderr or r.stdout}",
                "error",
            )
            return False, False

        restart = '"RestartNeeded":true' in r.stdout.replace(" ", "")
        self.log("Monitor de porta LPR ativado.", "ok")
        if restart:
            self.log(
                "O Windows exige reinicialização para usar o monitor LPR.",
                "warn",
            )
        return True, restart

    def conflicting_queues(self, profile: PrinterProfile) -> list[dict]:
        script = f"""
        $expected='{ps_quote(profile.expected_driver)}'
        $share='{ps_quote(profile.share_name)}'
        $local='{ps_quote(profile.local_printer_name)}'
        $client='{ps_quote(profile.client_queue_name)}'
        $path='\\\\{ps_quote(profile.server_name)}\\{ps_quote(profile.share_name)}'
        $items=Get-Printer -ErrorAction SilentlyContinue | Where-Object {{
          $_.Name -eq $client -or
          $_.Name -eq $path -or
          $_.Name -like "*$share*" -or
          (
            $_.DriverName -eq 'Generic / Text Only' -and
            (
              $_.PortName -eq $expected -or
              $_.PortName -eq $share -or
              $_.PortName -eq $local -or
              $_.Name -eq 'Generic / Text Only'
            )
          )
        }} | Select-Object Name,DriverName,PortName,Shared,ShareName,Type
        $items | ConvertTo-Json -Compress
        """
        r = powershell(script)
        if not r.ok or not r.stdout:
            return []
        try:
            import json
            value = json.loads(r.stdout)
            return [value] if isinstance(value, dict) else list(value or [])
        except Exception:
            return []

    def cleanup_client_conflicts(self, profile: PrinterProfile) -> bool:
        conflicts = self.conflicting_queues(profile)
        if conflicts:
            for item in conflicts:
                self.log(
                    "Removendo fila conflitante: "
                    f"{item.get('Name')} | Driver: {item.get('DriverName')} | "
                    f"Porta: {item.get('PortName')}",
                    "warn",
                )

        lpr_port = f"LPR_{profile.server_name}_{profile.share_name}"
        script = f"""
        $expected='{ps_quote(profile.expected_driver)}'
        $share='{ps_quote(profile.share_name)}'
        $local='{ps_quote(profile.local_printer_name)}'
        $client='{ps_quote(profile.client_queue_name)}'
        $path='\\\\{ps_quote(profile.server_name)}\\{ps_quote(profile.share_name)}'
        $lpr='{ps_quote(lpr_port)}'

        Get-Printer -ErrorAction SilentlyContinue | Where-Object {{
          $_.Name -eq $client -or
          $_.Name -eq $path -or
          $_.Name -like "*$share*" -or
          $_.PortName -eq $lpr -or
          (
            $_.DriverName -eq 'Generic / Text Only' -and
            (
              $_.PortName -eq $expected -or
              $_.PortName -eq $share -or
              $_.PortName -eq $local -or
              $_.Name -eq 'Generic / Text Only'
            )
          )
        }} | ForEach-Object {{
          Remove-Printer -Name $_.Name -ErrorAction SilentlyContinue
        }}

        Start-Sleep -Seconds 2
        $used=@(Get-Printer -ErrorAction SilentlyContinue |
          Select-Object -ExpandProperty PortName)

        Get-PrinterPort -ErrorAction SilentlyContinue | Where-Object {{
          ($_.Name -eq $lpr -or $_.Name -eq $expected) -and
          $used -notcontains $_.Name
        }} | ForEach-Object {{
          Remove-PrinterPort -Name $_.Name -ErrorAction SilentlyContinue
        }}

        Restart-Service Spooler -Force
        """
        r = powershell(script, timeout=120)
        self.log(
            "Filas e portas conflitantes foram limpas."
            if r.ok
            else f"Falha limpando conflitos: {r.stderr or r.stdout}",
            "ok" if r.ok else "error",
        )
        return r.ok

    def lpr_queue_exists(self, profile: PrinterProfile) -> bool:
        lpr_port = f"LPR_{profile.server_name}_{profile.share_name}"
        r = powershell(
            f"$p=Get-Printer -Name '{ps_quote(profile.client_queue_name)}' "
            "-ErrorAction SilentlyContinue;"
            f"if($p -and $p.DriverName -eq "
            f"'{ps_quote(profile.expected_driver)}' -and "
            f"$p.PortName -eq '{ps_quote(lpr_port)}'){{exit 0}}else{{exit 2}}"
        )
        return r.ok

    def rebuild_client_queue_lpr(
        self,
        profile: PrinterProfile,
        *,
        force_cleanup: bool = True,
    ) -> tuple[bool, bool]:
        """Recria a fila local usando LPR e o driver já instalado."""
        self.log(
            "Iniciando reconstrução profunda da fila do cliente...",
            "info",
        )

        enabled, restart = self.enable_lpr_client()
        if not enabled:
            return False, False
        if restart:
            return False, True

        if force_cleanup and not self.cleanup_client_conflicts(profile):
            return False, False

        driver = powershell(
            f"$d=Get-PrinterDriver -Name "
            f"'{ps_quote(profile.expected_driver)}' "
            "-ErrorAction SilentlyContinue;"
            "if($d){exit 0}else{exit 2}"
        )
        if not driver.ok:
            self.log(
                f"O driver {profile.expected_driver} não está instalado.",
                "error",
            )
            return False, False

        server = profile.server_ip or profile.server_name
        port_ok, detail = tcp_test(server, 515, timeout=4.0)
        if not port_ok:
            self.log(
                f"O servidor não respondeu na porta LPD 515: {detail}",
                "error",
            )
            self.log(
                "Execute a versão 4.2 no CF e use 'Reparo automático seguro' "
                "para ativar o fallback LPD do servidor.",
                "warn",
            )
            return False, False

        lpr_port = f"LPR_{profile.server_name}_{profile.share_name}"
        script = f"""
        $portName='{ps_quote(lpr_port)}'
        $hostName='{ps_quote(profile.server_name)}'
        $queueName='{ps_quote(profile.share_name)}'
        $printerName='{ps_quote(profile.client_queue_name)}'
        $driverName='{ps_quote(profile.expected_driver)}'

        if(Get-Printer -Name $printerName -ErrorAction SilentlyContinue){{
          Remove-Printer -Name $printerName -ErrorAction SilentlyContinue
        }}

        $existing=Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue
        if(-not $existing){{
          $port=([WMIClass]'Win32_TCPIPPrinterPort').CreateInstance()
          $port.Name=$portName
          $port.Protocol=2
          $port.HostAddress=$hostName
          $port.Queue=$queueName
          $port.ByteCount=$true
          $port.SNMPEnabled=$false
          [void]$port.Put()
        }}

        Add-Printer -Name $printerName -DriverName $driverName `
          -PortName $portName -ErrorAction Stop
        Restart-Service Spooler -Force
        """
        r = powershell(script, timeout=150)
        if not r.ok:
            self.log(
                f"Falha recriando a fila por LPR: {r.stderr or r.stdout}",
                "error",
            )
            return False, False

        import time
        time.sleep(4)
        if self.lpr_queue_exists(profile):
            self.log(
                f"Fila recriada: {profile.client_queue_name} | "
                f"Driver: {profile.expected_driver} | Porta: {lpr_port}",
                "ok",
            )
            return True, False

        self.log(
            "A criação terminou, mas a fila não foi confirmada.",
            "error",
        )
        return False, False

    def import_driver_inf(self, inf_path: str, expected_name: str = "") -> bool:
        r = run(
            ["pnputil.exe", "/add-driver", inf_path, "/install"],
            timeout=180,
        )
        if not r.ok:
            self.log(f"Falha importando INF: {r.stderr or r.stdout}", "error")
            return False
        if expected_name:
            powershell(
                f"Add-PrinterDriver -Name '{ps_quote(expected_name)}' "
                "-ErrorAction SilentlyContinue",
                timeout=90,
            )
        self.log("Pacote de driver importado no Driver Store.", "ok")
        return True

    def direct_tcp_install(self, profile: PrinterProfile) -> bool:
        if not profile.direct_printer_ip:
            self.log("Informe o IP próprio da impressora para o modo TCP direto.", "error")
            return False
        ok, detail = tcp_test(profile.direct_printer_ip, profile.direct_printer_port)
        if not ok:
            self.log(
                f"A impressora não responde em {profile.direct_printer_ip}:"
                f"{profile.direct_printer_port} — {detail}",
                "error",
            )
            return False
        port_name = f"IP_{profile.direct_printer_ip}"
        queue_name = f"{profile.share_name} - TCP"
        r = powershell(
            f"$port='{ps_quote(port_name)}';"
            f"if(-not(Get-PrinterPort -Name $port -ErrorAction SilentlyContinue)){{"
            f"Add-PrinterPort -Name $port -PrinterHostAddress "
            f"'{ps_quote(profile.direct_printer_ip)}' -PortNumber "
            f"{int(profile.direct_printer_port)}}};"
            f"if(Get-Printer -Name '{ps_quote(queue_name)}' "
            "-ErrorAction SilentlyContinue){{"
            f"Remove-Printer -Name '{ps_quote(queue_name)}'}};"
            f"Add-Printer -Name '{ps_quote(queue_name)}' "
            f"-DriverName '{ps_quote(profile.expected_driver)}' "
            f"-PortName $port -ErrorAction Stop",
            timeout=120,
        )
        self.log(
            f"Fila TCP direta criada: {queue_name}."
            if r.ok else f"Falha no modo TCP direto: {r.stderr}",
            "ok" if r.ok else "error",
        )
        return r.ok
