from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class PrinterProfile:
    name: str = "Exemplo - Impressora compartilhada"
    server_name: str = "PRINT-SERVER"
    server_ip: str = "192.168.1.50"
    share_name: str = "SharedPrinter"
    network_user: str = "PrinterUser"
    local_printer_name: str = "Local Printer"
    expected_driver: str = "Printer Driver"
    client_queue_name: str = "Shared Printer (PRINT-SERVER)"
    enable_lpr_fallback: bool = True
    direct_printer_ip: str = ""
    direct_printer_port: int = 9100
    direct_printer_port: int = 9100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrinterProfile":
        allowed = cls.__dataclass_fields__.keys()
        clean = {k: data[k] for k in allowed if k in data}
        return cls(**clean)


@dataclass
class CheckResult:
    key: str
    title: str
    status: str  # ok, warn, error, info
    detail: str
    fix_id: str = ""
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
