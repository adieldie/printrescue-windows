from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from ctypes import wintypes


RESOURCETYPE_DISK = 1
CONNECT_UPDATE_PROFILE = 0x00000001


class NETRESOURCEW(ctypes.Structure):
    _fields_ = [
        ("dwScope", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
        ("dwDisplayType", wintypes.DWORD),
        ("dwUsage", wintypes.DWORD),
        ("lpLocalName", wintypes.LPWSTR),
        ("lpRemoteName", wintypes.LPWSTR),
        ("lpComment", wintypes.LPWSTR),
        ("lpProvider", wintypes.LPWSTR),
    ]


@dataclass
class NetworkAuthResult:
    ok: bool
    code: int
    message: str
    remote: str


_ERROR_MESSAGES = {
    0: "Conexão concluída.",
    5: "Acesso negado pelo servidor.",
    53: "O caminho de rede não foi encontrado.",
    64: "O nome de rede deixou de estar disponível.",
    67: "O nome do compartilhamento não foi encontrado.",
    85: "O recurso já está conectado.",
    86: "A senha informada está incorreta.",
    1219: (
        "O Windows já possui uma conexão com esse servidor usando outro usuário. "
        "As sessões conflitantes precisam ser encerradas."
    ),
    1203: "Nenhum provedor de rede aceitou o caminho informado.",
    1326: "Usuário ou senha incorretos.",
    2250: "A conexão de rede não existe.",
}


def explain_error(code: int) -> str:
    if code in _ERROR_MESSAGES:
        return _ERROR_MESSAGES[code]
    try:
        detail = ctypes.FormatError(code).strip()
    except Exception:
        detail = ""
    return detail or f"Erro de rede do Windows: {code}"


def _mpr():
    if os.name != "nt":
        raise RuntimeError("A API de rede está disponível somente no Windows.")

    dll = ctypes.WinDLL("mpr", use_last_error=True)

    dll.WNetAddConnection2W.argtypes = [
        ctypes.POINTER(NETRESOURCEW),
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    ]
    dll.WNetAddConnection2W.restype = wintypes.DWORD

    dll.WNetCancelConnection2W.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.BOOL,
    ]
    dll.WNetCancelConnection2W.restype = wintypes.DWORD
    return dll


def connect(
    remote: str,
    *,
    username: str | None = None,
    password: str | None = None,
    persistent: bool = False,
) -> NetworkAuthResult:
    resource = NETRESOURCEW()
    resource.dwType = RESOURCETYPE_DISK
    resource.lpRemoteName = remote

    flags = CONNECT_UPDATE_PROFILE if persistent else 0
    code = int(
        _mpr().WNetAddConnection2W(
            ctypes.byref(resource),
            password,
            username,
            flags,
        )
    )
    return NetworkAuthResult(
        ok=code == 0,
        code=code,
        message=explain_error(code),
        remote=remote,
    )


def disconnect(remote: str, *, force: bool = True) -> NetworkAuthResult:
    code = int(_mpr().WNetCancelConnection2W(remote, 0, bool(force)))
    # 2250 means the connection did not exist. For cleanup this is harmless.
    ok = code in (0, 2250)
    return NetworkAuthResult(
        ok=ok,
        code=code,
        message=explain_error(code),
        remote=remote,
    )
