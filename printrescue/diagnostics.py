from __future__ import annotations

import os
import platform
from pathlib import Path

from .models import CheckResult, PrinterProfile
from .runner import (
    hostname,
    is_admin,
    parse_json_output,
    powershell,
    ps_quote,
    resolve_ipv4,
    tcp_test,
)


class Diagnostics:
    def __init__(self, emit) -> None:
        self.emit = emit

    def mode(self, profile: PrinterProfile) -> str:
        return "server" if hostname().casefold() == profile.server_name.casefold() else "client"

    def all(self, profile: PrinterProfile) -> list[CheckResult]:
        results: list[CheckResult] = []
        results.extend(self.environment(profile))
        results.extend(self.services(profile))
        results.extend(self.network(profile))
        if self.mode(profile) == "server":
            results.extend(self.server(profile))
        else:
            results.extend(self.client(profile))
        return results

    def environment(self, profile: PrinterProfile) -> list[CheckResult]:
        current_mode = self.mode(profile)
        return [
            CheckResult(
                "windows",
                "Sistema operacional",
                "ok" if os.name == "nt" else "error",
                f"{platform.system()} {platform.release()} {platform.version()}",
            ),
            CheckResult(
                "admin",
                "Permissão de administrador",
                "ok" if is_admin() else "error",
                "Executando como administrador." if is_admin() else "O aplicativo precisa ser elevado.",
                "elevate",
            ),
            CheckResult(
                "mode",
                "Modo detectado",
                "ok",
                f"{'SERVIDOR' if current_mode == 'server' else 'CLIENTE'} — computador {hostname()}",
            ),
        ]

    def services(self, profile: PrinterProfile) -> list[CheckResult]:
        names = ["Spooler", "LanmanWorkstation"]
        if self.mode(profile) == "server":
            names.extend(["LanmanServer", "FDResPub", "fdPHost"])

        results = []
        for name in names:
            r = powershell(
                f"$s=Get-Service -Name '{ps_quote(name)}' -ErrorAction SilentlyContinue;"
                "if($s){"
                "[pscustomobject]@{"
                "Name=$s.Name;"
                "Status=$s.Status.ToString();"
                "StartType=$s.StartType.ToString()"
                "} | ConvertTo-Json -Compress"
                "}else{exit 2}"
            )
            data = parse_json_output(r, {})
            status_text = str(data.get("Status", "")).strip()
            start_type_text = str(data.get("StartType", "")).strip()
            running = r.ok and status_text.casefold() == "running"
            results.append(
                CheckResult(
                    f"service:{name}",
                    f"Serviço {name}",
                    "ok" if running else "error",
                    (
                        f"Estado: {data.get('Status')} | Inicialização: {data.get('StartType')}"
                        if data
                        else (r.stderr or "Serviço ausente ou inacessível.")
                    ),
                    "services",
                    data if isinstance(data, dict) else {},
                )
            )
        return results

    def network(self, profile: PrinterProfile) -> list[CheckResult]:
        results = []
        r = powershell(
            "Get-NetConnectionProfile -ErrorAction SilentlyContinue | "
            "Where-Object {$_.IPv4Connectivity -ne 'Disconnected'} | "
            "Select-Object Name,InterfaceAlias,NetworkCategory,IPv4Connectivity | "
            "ConvertTo-Json -Compress"
        )
        data = parse_json_output(r, [])
        if isinstance(data, dict):
            data = [data]
        private = bool(data) and all(x.get("NetworkCategory") != "Public" for x in data)
        results.append(
            CheckResult(
                "network_profile",
                "Perfil da rede",
                "ok" if private else "warn",
                "Rede privada." if private else "Existe uma rede pública ativa.",
                "network_private",
                {"profiles": data},
            )
        )

        if self.mode(profile) == "client":
            for port, label in ((445, "SMB"), (135, "RPC Endpoint Mapper")):
                ok, detail = tcp_test(profile.server_ip or profile.server_name, port)
                results.append(
                    CheckResult(
                        f"port:{port}",
                        f"{label} — porta {port}",
                        "ok" if ok else "error",
                        detail,
                        "firewall_rpc" if port == 135 else "firewall_smb",
                    )
                )

            resolved = resolve_ipv4(profile.server_name)
            name_ok = bool(resolved) and (
                not profile.server_ip or resolved == profile.server_ip
            )
            results.append(
                CheckResult(
                    "dns",
                    "Nome do servidor",
                    "ok" if name_ok else "warn",
                    f"{profile.server_name} → {resolved or 'não resolvido'}; esperado: {profile.server_ip}",
                    "hosts",
                )
            )
        return results

    def _printers(self):
        r = powershell(
            "Get-Printer -ErrorAction SilentlyContinue | "
            "Select-Object Name,Type,DriverName,PortName,Shared,ShareName,PrinterStatus | "
            "ConvertTo-Json -Compress"
        )
        data = parse_json_output(r, [])
        if isinstance(data, dict):
            data = [data]
        return data or []

    def server(self, profile: PrinterProfile) -> list[CheckResult]:
        results = []
        printers = self._printers()
        local = next(
            (p for p in printers if p.get("Name", "").casefold() == profile.local_printer_name.casefold()),
            None,
        )
        results.append(
            CheckResult(
                "server_local_printer",
                "Impressora física no servidor",
                "ok" if local else "error",
                (
                    f"{local.get('Name')} | Driver: {local.get('DriverName')} | Porta: {local.get('PortName')}"
                    if local
                    else f"Não encontrada: {profile.local_printer_name}"
                ),
                "server_share",
                {"printer": local, "all_printers": printers},
            )
        )

        shared = next(
            (
                p
                for p in printers
                if p.get("Shared")
                and str(p.get("ShareName", "")).casefold() == profile.share_name.casefold()
            ),
            None,
        )
        results.append(
            CheckResult(
                "server_share",
                "Compartilhamento da fila",
                "ok" if shared else "error",
                (
                    f"\\\\{profile.server_name}\\{profile.share_name} está ativo."
                    if shared
                    else f"O compartilhamento {profile.share_name} não está ativo."
                ),
                "server_share",
                {"printer": shared},
            )
        )

        u = powershell(
            f"$u=Get-LocalUser -Name '{ps_quote(profile.network_user)}' -ErrorAction SilentlyContinue;"
            "if($u){$u | Select-Object Name,Enabled,PasswordExpires | ConvertTo-Json -Compress}else{exit 2}"
        )
        user = parse_json_output(u, {})
        results.append(
            CheckResult(
                "server_user",
                "Usuário da rede",
                "ok" if u.ok and user.get("Enabled") else "error",
                (
                    f"{profile.server_name}\\{profile.network_user} ativo."
                    if u.ok and user.get("Enabled")
                    else "Usuário ausente ou desativado."
                ),
                "server_user",
                user if isinstance(user, dict) else {},
            )
        )

        rpc = powershell(
            "$p='HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\Printers\\RPC';"
            "$v=(Get-ItemProperty -Path $p -Name RpcProtocols -ErrorAction SilentlyContinue).RpcProtocols;"
            "if($null -ne $v){Write-Output $v}else{Write-Output 0}"
        )
        rpc_ok = rpc.stdout.strip() in {"3", "7"}
        results.append(
            CheckResult(
                "rpc_server",
                "RPC de impressão do servidor",
                "ok" if rpc_ok else "warn",
                f"RpcProtocols={rpc.stdout.strip() or 'não definido'}",
                "rpc_server",
            )
        )
        return results

    def client(self, profile: PrinterProfile) -> list[CheckResult]:
        results = []
        path = rf"\\{profile.server_name}\{profile.share_name}"
        lpr_port = f"LPR_{profile.server_name}_{profile.share_name}"
        printers = self._printers()

        installed = next(
            (
                p for p in printers
                if str(p.get("Name", "")).casefold() == path.casefold()
                or str(p.get("Name", "")).casefold()
                == profile.client_queue_name.casefold()
                or str(p.get("PortName", "")).casefold() == lpr_port.casefold()
                or (
                    p.get("Type") == "Connection"
                    and profile.share_name.casefold()
                    in str(p.get("Name", "")).casefold()
                )
            ),
            None,
        )
        results.append(
            CheckResult(
                "client_queue",
                "Fila no cliente",
                "ok" if installed else "error",
                (
                    f"Instalada: {installed.get('Name')} | "
                    f"Driver: {installed.get('DriverName')} | "
                    f"Porta: {installed.get('PortName')}"
                    if installed
                    else f"Não instalada: {path}"
                ),
                "client_install",
                {"printer": installed},
            )
        )

        conflicts = [
            p for p in printers
            if (
                str(p.get("DriverName", "")).casefold()
                == "generic / text only"
                and (
                    str(p.get("PortName", "")).casefold()
                    in {
                        profile.expected_driver.casefold(),
                        profile.share_name.casefold(),
                        profile.local_printer_name.casefold(),
                    }
                    or str(p.get("Name", "")).casefold()
                    == "generic / text only"
                )
            )
        ]
        results.append(
            CheckResult(
                "client_conflicts",
                "Filas conflitantes",
                "warn" if conflicts else "ok",
                (
                    "Detectada fila incorreta: "
                    + ", ".join(
                        f"{p.get('Name')} / {p.get('DriverName')} / "
                        f"porta {p.get('PortName')}"
                        for p in conflicts
                    )
                    if conflicts
                    else "Nenhuma fila conflitante detectada."
                ),
                "client_rebuild",
                {"conflicts": conflicts},
            )
        )

        d = powershell(
            f"$d=Get-PrinterDriver -Name '{ps_quote(profile.expected_driver)}' "
            "-ErrorAction SilentlyContinue;if($d){$d.Name}else{exit 2}"
        )
        results.append(
            CheckResult(
                "client_driver",
                "Driver esperado",
                "ok" if d.ok else "warn",
                (
                    f"Driver instalado: {profile.expected_driver}"
                    if d.ok
                    else f"Driver não localizado: {profile.expected_driver}"
                ),
                "driver_import",
            )
        )

        c = powershell(
            f"$x=cmdkey /list; if(($x -join \"`n\") -match "
            f"'{ps_quote(profile.server_name)}'){{exit 0}}else{{exit 2}}"
        )
        results.append(
            CheckResult(
                "credential",
                "Credencial armazenada",
                "ok" if c.ok else "warn",
                (
                    "Existe uma credencial salva, mas ela ainda precisa ser "
                    "validada em uma conexão real."
                    if c.ok
                    else "Credencial não encontrada."
                ),
                "credential",
            )
        )

        rpc = powershell(
            "$p='HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\Printers\\RPC';"
            "$v=(Get-ItemProperty -Path $p -Name RpcUseNamedPipeProtocol "
            "-ErrorAction SilentlyContinue).RpcUseNamedPipeProtocol;"
            "if($null -ne $v){Write-Output $v}else{Write-Output 0}"
        )
        results.append(
            CheckResult(
                "rpc_client",
                "RPC de impressão do cliente",
                "ok" if rpc.stdout.strip() == "1" else "warn",
                f"RpcUseNamedPipeProtocol={rpc.stdout.strip() or 'não definido'}",
                "rpc_client",
            )
        )

        if profile.enable_lpr_fallback:
            feature = powershell(
                "$f=Get-WindowsOptionalFeature -Online "
                "-FeatureName Printing-Foundation-LPRPortMonitor "
                "-ErrorAction SilentlyContinue;"
                "if($f){$f.State.ToString()}else{'Unavailable'}"
            )
            feature_state = feature.stdout.strip()
            results.append(
                CheckResult(
                    "lpr_client",
                    "Fallback LPR no cliente",
                    "ok" if feature_state == "Enabled" else "warn",
                    f"Printing-Foundation-LPRPortMonitor={feature_state}",
                    "client_rebuild",
                )
            )

        return results

