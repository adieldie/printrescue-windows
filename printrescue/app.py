from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .diagnostics import Diagnostics
from .models import CheckResult, PrinterProfile
from .repairs import Repairs
from .runner import elevate_current_process, hostname, is_admin, powershell
from .storage import Storage


class PrintRescueApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"PrintRescue Windows v{__version__}")
        self.root.geometry("1180x800")
        self.root.minsize(980, 700)

        self.storage = Storage()
        self.profiles = self.storage.load_profiles()
        self.settings = self.storage.load_settings()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.last_results: list[CheckResult] = []
        self.reboot_required = False

        self.profile_name = tk.StringVar()
        self.server_name = tk.StringVar()
        self.server_ip = tk.StringVar()
        self.share_name = tk.StringVar()
        self.network_user = tk.StringVar()
        self.local_printer_name = tk.StringVar()
        self.expected_driver = tk.StringVar()
        self.client_queue_name = tk.StringVar()
        self.enable_lpr_fallback = tk.BooleanVar(value=True)
        self.direct_printer_ip = tk.StringVar()
        self.direct_printer_port = tk.StringVar(value="9100")
        self.mode_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Pronto")

        self._build()
        self._load_profile()
        self._update_mode()
        self._poll()

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(
            top,
            text="PrintRescue Windows",
            font=("Segoe UI", 21, "bold"),
        ).pack(side="left")
        ttk.Label(
            top,
            text=f"v{__version__}",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=8, pady=(8, 0))
        self.admin_label = ttk.Label(
            top,
            text="ADMIN" if is_admin() else "SEM ADMIN",
        )
        self.admin_label.pack(side="right")

        ttk.Label(
            outer,
            text=(
                "Diagnóstico e reparo de impressoras compartilhadas no Windows, "
                "com backup, perfis, RPC, firewall, credenciais, drivers e múltiplos "
                "métodos de instalação."
            ),
            wraplength=1100,
        ).pack(anchor="w", pady=(2, 10))

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)

        self.dashboard = ttk.Frame(self.tabs, padding=10)
        self.profile_tab = ttk.Frame(self.tabs, padding=10)
        self.driver_tab = ttk.Frame(self.tabs, padding=10)
        self.advanced_tab = ttk.Frame(self.tabs, padding=10)
        self.log_tab = ttk.Frame(self.tabs, padding=10)

        self.tabs.add(self.dashboard, text="Diagnóstico e reparo")
        self.tabs.add(self.profile_tab, text="Perfis")
        self.tabs.add(self.driver_tab, text="Drivers")
        self.tabs.add(self.advanced_tab, text="Avançado")
        self.tabs.add(self.log_tab, text="Log")

        self._build_dashboard()
        self._build_profile()
        self._build_drivers()
        self._build_advanced()
        self._build_log()

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(8, 0))
        self.progress = ttk.Progressbar(bottom, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left", padx=(10, 0))

    def _build_dashboard(self) -> None:
        bar = ttk.Frame(self.dashboard)
        bar.pack(fill="x")

        ttk.Label(bar, text="Perfil:").pack(side="left")
        self.profile_combo = ttk.Combobox(
            bar,
            textvariable=self.profile_name,
            state="readonly",
            width=30,
        )
        self.profile_combo.pack(side="left", padx=6)
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _e: self.select_profile())

        ttk.Label(bar, textvariable=self.mode_var, font=("Segoe UI", 10, "bold")).pack(
            side="left", padx=10
        )

        self.btn_diag = ttk.Button(bar, text="Verificar tudo", command=self.start_diagnostic)
        self.btn_diag.pack(side="right", padx=4)
        self.btn_auto = ttk.Button(bar, text="Reparo automático seguro", command=self.start_auto)
        self.btn_auto.pack(side="right", padx=4)

        self.tree = ttk.Treeview(
            self.dashboard,
            columns=("status", "detail"),
            show="tree headings",
            height=20,
        )
        self.tree.heading("#0", text="Verificação")
        self.tree.heading("status", text="Estado")
        self.tree.heading("detail", text="Detalhes")
        self.tree.column("#0", width=260)
        self.tree.column("status", width=90, anchor="center")
        self.tree.column("detail", width=700)
        self.tree.pack(fill="both", expand=True, pady=(10, 0))

        self.tree.tag_configure("ok", foreground="#15803d")
        self.tree.tag_configure("warn", foreground="#a16207")
        self.tree.tag_configure("error", foreground="#b91c1c")
        self.tree.tag_configure("info", foreground="#1d4ed8")

        action = ttk.Frame(self.dashboard)
        action.pack(fill="x", pady=(8, 0))
        ttk.Button(action, text="Reparar servidor de impressão", command=lambda: self.start_mode("server")).pack(
            side="left", padx=4
        )
        ttk.Button(action, text="Reparar este cliente", command=lambda: self.start_mode("client")).pack(
            side="left", padx=4
        )
        ttk.Button(
            action,
            text="Testar login no servidor",
            command=self.start_test_server_login,
        ).pack(side="left", padx=4)
        ttk.Button(
            action,
            text="Recriar fila do zero",
            command=self.start_rebuild_client,
        ).pack(side="left", padx=4)
        ttk.Button(action, text="Imprimir página de teste", command=self.print_test).pack(
            side="left", padx=4
        )
        ttk.Button(action, text="Exportar relatório", command=self.export_report).pack(
            side="left", padx=4
        )
        ttk.Button(action, text="Abrir impressoras do Windows", command=self.open_printers).pack(
            side="right", padx=4
        )

    def _build_profile(self) -> None:
        frame = ttk.LabelFrame(self.profile_tab, text="Configuração reutilizável", padding=10)
        frame.pack(fill="x")

        rows = [
            ("Nome do perfil", self.profile_name),
            ("Nome do servidor", self.server_name),
            ("IP do servidor", self.server_ip),
            ("Nome compartilhado", self.share_name),
            ("Usuário de rede", self.network_user),
            ("Impressora local no servidor", self.local_printer_name),
            ("Driver esperado", self.expected_driver),
            ("Nome da fila no cliente", self.client_queue_name),
            ("IP próprio da impressora (opcional)", self.direct_printer_ip),
            ("Porta RAW/TCP (opcional)", self.direct_printer_port),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(frame, text=label + ":").grid(row=i, column=0, sticky="w", padx=5, pady=5)
            ttk.Entry(frame, textvariable=var).grid(
                row=i, column=1, sticky="ew", padx=5, pady=5
            )
        ttk.Checkbutton(
            frame,
            text="Usar fallback LPR quando o Windows bloquear Point and Print",
            variable=self.enable_lpr_fallback,
        ).grid(
            row=len(rows),
            column=0,
            columnspan=2,
            sticky="w",
            padx=5,
            pady=8,
        )
        frame.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self.profile_tab)
        buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="Novo perfil", command=self.new_profile).pack(side="left", padx=4)
        ttk.Button(buttons, text="Salvar perfil", command=self.save_profile).pack(side="left", padx=4)
        ttk.Button(buttons, text="Excluir perfil", command=self.delete_profile).pack(side="left", padx=4)
        ttk.Button(buttons, text="Detectar impressoras e drivers", command=self.detect_devices).pack(
            side="left", padx=4
        )

        self.device_text = tk.Text(self.profile_tab, height=17, wrap="word", font=("Consolas", 9))
        self.device_text.pack(fill="both", expand=True)

    def _build_drivers(self) -> None:
        ttk.Label(
            self.driver_tab,
            text=(
                "Importe o arquivo .INF oficial do fabricante. O aplicativo usa o "
                "PNPUtil do Windows e não baixa drivers de sites desconhecidos."
            ),
            wraplength=1000,
        ).pack(anchor="w")

        bar = ttk.Frame(self.driver_tab)
        bar.pack(fill="x", pady=10)
        ttk.Button(bar, text="Importar driver .INF", command=self.import_inf).pack(side="left", padx=4)
        ttk.Button(bar, text="Listar drivers instalados", command=self.list_drivers).pack(
            side="left", padx=4
        )
        ttk.Button(bar, text="Abrir Gerenciador de Dispositivos", command=self.open_device_manager).pack(
            side="left", padx=4
        )

        self.driver_text = tk.Text(self.driver_tab, wrap="none", font=("Consolas", 9))
        self.driver_text.pack(fill="both", expand=True)

    def _build_advanced(self) -> None:
        safe = ttk.LabelFrame(self.advanced_tab, text="Ferramentas seguras", padding=10)
        safe.pack(fill="x")
        ttk.Button(safe, text="Criar backup agora", command=self.create_backup).pack(
            side="left", padx=4
        )
        ttk.Button(safe, text="Restaurar backup de registro", command=self.restore_backup).pack(
            side="left", padx=4
        )
        ttk.Button(safe, text="Reiniciar Spooler", command=self.restart_spooler).pack(
            side="left", padx=4
        )
        ttk.Button(safe, text="Abrir Gerenciador de Credenciais", command=self.open_credentials).pack(
            side="left", padx=4
        )

        tcp = ttk.LabelFrame(
            self.advanced_tab,
            text="Fallback TCP direto — somente para impressoras com IP próprio",
            padding=10,
        )
        tcp.pack(fill="x", pady=10)
        ttk.Label(
            tcp,
            text=(
                "Não use este modo para uma impressora USB compartilhada por outro computador. Ele cria uma fila "
                "direta para uma impressora de rede que responda em uma porta RAW/TCP."
            ),
            wraplength=1000,
        ).pack(anchor="w")
        ttk.Button(tcp, text="Instalar por TCP direto", command=self.direct_tcp).pack(
            anchor="w", pady=8
        )

        risk = ttk.LabelFrame(
            self.advanced_tab,
            text="Políticas sensíveis — não alteradas automaticamente",
            padding=10,
        )
        risk.pack(fill="both", expand=True)
        ttk.Label(
            risk,
            text=(
                "O PrintRescue não desativa automaticamente as proteções de Point and Print, "
                "não habilita SMB1 e não libera acesso de convidado. Essas mudanças podem "
                "reduzir a segurança. Use os botões abaixo apenas para inspecionar."
            ),
            wraplength=1000,
        ).pack(anchor="w")
        ttk.Button(risk, text="Abrir políticas locais", command=self.open_gpedit).pack(
            anchor="w", pady=5
        )
        ttk.Button(risk, text="Abrir chave de políticas de impressora", command=self.open_registry).pack(
            anchor="w", pady=5
        )

    def _build_log(self) -> None:
        self.log_text = tk.Text(
            self.log_tab,
            wrap="word",
            bg="#111827",
            fg="#e5e7eb",
            insertbackground="white",
            font=("Consolas", 10),
        )
        self.log_text.pack(fill="both", expand=True)
        for tag, color in {
            "ok": "#86efac",
            "warn": "#fde68a",
            "error": "#fca5a5",
            "info": "#93c5fd",
            "title": "#c4b5fd",
        }.items():
            self.log_text.tag_configure(tag, foreground=color)

    def profile(self) -> PrinterProfile:
        try:
            port = int(self.direct_printer_port.get().strip() or "9100")
        except ValueError:
            port = 9100
        return PrinterProfile(
            name=self.profile_name.get().strip() or "Novo perfil",
            server_name=self.server_name.get().strip(),
            server_ip=self.server_ip.get().strip(),
            share_name=self.share_name.get().strip(),
            network_user=self.network_user.get().strip(),
            local_printer_name=self.local_printer_name.get().strip(),
            expected_driver=self.expected_driver.get().strip(),
            client_queue_name=self.client_queue_name.get().strip()
            or f"{self.share_name.get().strip()} ({self.server_name.get().strip()})",
            enable_lpr_fallback=bool(self.enable_lpr_fallback.get()),
            direct_printer_ip=self.direct_printer_ip.get().strip(),
            direct_printer_port=port,
        )

    def apply_profile(self, p: PrinterProfile) -> None:
        self.profile_name.set(p.name)
        self.server_name.set(p.server_name)
        self.server_ip.set(p.server_ip)
        self.share_name.set(p.share_name)
        self.network_user.set(p.network_user)
        self.local_printer_name.set(p.local_printer_name)
        self.expected_driver.set(p.expected_driver)
        self.client_queue_name.set(p.client_queue_name)
        self.enable_lpr_fallback.set(p.enable_lpr_fallback)
        self.direct_printer_ip.set(p.direct_printer_ip)
        self.direct_printer_port.set(str(p.direct_printer_port))
        self._update_mode()

    def _load_profile(self) -> None:
        names = [p.name for p in self.profiles]
        self.profile_combo.configure(values=names)
        last = self.settings.get("last_profile")
        p = next((x for x in self.profiles if x.name == last), self.profiles[0])
        self.apply_profile(p)

    def select_profile(self) -> None:
        p = next((x for x in self.profiles if x.name == self.profile_name.get()), None)
        if p:
            self.apply_profile(p)
            self.settings["last_profile"] = p.name
            self.storage.save_settings(self.settings)

    def save_profile(self) -> None:
        p = self.profile()
        if not p.server_name or not p.share_name:
            messagebox.showerror("PrintRescue", "Servidor e compartilhamento são obrigatórios.")
            return
        idx = next((i for i, x in enumerate(self.profiles) if x.name == p.name), None)
        if idx is None:
            self.profiles.append(p)
        else:
            self.profiles[idx] = p
        self.storage.save_profiles(self.profiles)
        self.profile_combo.configure(values=[x.name for x in self.profiles])
        self.settings["last_profile"] = p.name
        self.storage.save_settings(self.settings)
        self.log(f"Perfil '{p.name}' salvo.", "ok")

    def new_profile(self) -> None:
        name = simpledialog.askstring("PrintRescue", "Nome do novo perfil:", parent=self.root)
        if not name:
            return
        p = PrinterProfile(
            name=name.strip(),
            server_name="",
            server_ip="",
            share_name="",
            network_user="RedeImpressora",
            local_printer_name="",
            expected_driver="",
            client_queue_name="",
            enable_lpr_fallback=True,
        )
        self.profiles.append(p)
        self.storage.save_profiles(self.profiles)
        self.profile_combo.configure(values=[x.name for x in self.profiles])
        self.apply_profile(p)

    def delete_profile(self) -> None:
        if len(self.profiles) <= 1:
            messagebox.showwarning("PrintRescue", "Mantenha pelo menos um perfil.")
            return
        name = self.profile_name.get()
        if not messagebox.askyesno("PrintRescue", f"Excluir o perfil '{name}'?"):
            return
        self.profiles = [x for x in self.profiles if x.name != name]
        self.storage.save_profiles(self.profiles)
        self.profile_combo.configure(values=[x.name for x in self.profiles])
        self.apply_profile(self.profiles[0])

    def _update_mode(self) -> None:
        p = self.profile()
        mode = "SERVIDOR" if hostname().casefold() == p.server_name.casefold() else "CLIENTE"
        self.mode_var.set(f"{mode} — {hostname()}")

    def log(self, text: str, level: str = "info") -> None:
        self.events.put(("log", (text, level)))

    def set_status(self, text: str) -> None:
        self.events.put(("status", text))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    text, level = payload
                    stamp = datetime.now().strftime("%H:%M:%S")
                    self.log_text.insert("end", f"[{stamp}] {text}\n", level)
                    self.log_text.see("end")
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "results":
                    self.display_results(payload)
                elif kind == "done":
                    self.set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def set_busy(self, value: bool) -> None:
        self.busy = value
        state = "disabled" if value else "normal"
        self.btn_diag.configure(state=state)
        self.btn_auto.configure(state=state)
        if value:
            self.progress.start(10)
        else:
            self.progress.stop()
            self.status_var.set("Pronto")

    def background(self, func) -> None:
        if self.busy:
            return
        self.set_busy(True)

        def worker():
            try:
                func()
            except Exception as exc:
                self.log(f"Erro inesperado: {exc}", "error")
            finally:
                self.events.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def display_results(self, results: list[CheckResult]) -> None:
        self.last_results = results
        for item in self.tree.get_children():
            self.tree.delete(item)
        labels = {"ok": "OK", "warn": "ATENÇÃO", "error": "FALHA", "info": "INFO"}
        for r in results:
            self.tree.insert(
                "",
                "end",
                text=r.title,
                values=(labels.get(r.status, r.status), r.detail),
                tags=(r.status,),
            )

    def start_diagnostic(self) -> None:
        self.background(self._diagnostic)

    def _diagnostic(self) -> None:
        self.set_status("Executando diagnóstico...")
        d = Diagnostics(self.log)
        results = d.all(self.profile())
        self.events.put(("results", results))
        errors = sum(1 for x in results if x.status == "error")
        warnings = sum(1 for x in results if x.status == "warn")
        self.log(f"Diagnóstico concluído: {errors} falhas, {warnings} alertas.", "title")

    def start_auto(self) -> None:
        p = self.profile()
        mode = "server" if hostname().casefold() == p.server_name.casefold() else "client"
        self.start_mode(mode)

    def start_mode(self, mode: str) -> None:
        if not is_admin():
            messagebox.showerror("PrintRescue", "Execute o aplicativo como administrador.")
            return
        self.save_profile()
        self.background(lambda: self._repair(mode))

    def _repair(self, mode: str) -> None:
        p = self.profile()
        rep = Repairs(self.storage, self.log)
        rep.backup(p)
        self.set_status("Aplicando reparos seguros...")
        rep.set_private_network()
        rep.services(server=(mode == "server"))
        rep.firewall(server=(mode == "server"))

        if mode == "server":
            rep.rpc_server()
            password = None
            exists = powershell(
                f"if(Get-LocalUser -Name '{p.network_user.replace(chr(39), chr(39)*2)}' "
                "-ErrorAction SilentlyContinue){exit 0}else{exit 2}"
            ).ok
            if not exists:
                password = self.ask_password_sync(
                    f"Crie uma senha para {p.server_name}\\{p.network_user}",
                    confirm=True,
                )
            if not rep.create_or_update_user(p, password):
                return
            if not rep.share_printer(p):
                return
            rep.grant_print_permission(p)
            if p.enable_lpr_fallback:
                rep.enable_lpd_server(p)
        else:
            rep.rpc_client()
            rep.hosts(p)
            rep.remove_old_connection(p)

            auth_ok, auth_message, auth_code = rep.authenticate_saved(p)

            if not auth_ok:
                password = self.ask_password_sync(
                    f"Digite a senha de {p.server_name}\\{p.network_user}"
                )
                if password:
                    auth_ok, auth_message, auth_code = (
                        rep.authenticate_with_password(p, password)
                    )
                    # Minimize the lifetime of the plain-text password reference.
                    password = None
                else:
                    self.log(
                        "Senha não informada. A instalação SMB será ignorada.",
                        "warn",
                    )

            if auth_ok:
                installed, reboot = rep.install_shared_queue(p)
            elif p.enable_lpr_fallback:
                self.log(
                    "A autenticação SMB não foi aceita, mas o perfil permite "
                    "fallback LPR. Continuando sem depender da senha SMB...",
                    "warn",
                )
                installed, reboot = rep.rebuild_client_queue_lpr(
                    p,
                    force_cleanup=True,
                )
            else:
                self.log(
                    f"Não foi possível conectar ao servidor: {auth_message} "
                    f"(código {auth_code}).",
                    "error",
                )
                return

            self.reboot_required = reboot
            if installed:
                self.log("Cliente configurado e impressora instalada.", "ok")
            elif reboot:
                self.log("Reinicie este cliente para concluir a instalação.", "warn")
                self.ask_reboot()
            else:
                self.log(
                    "O Windows ainda não criou a fila. Consulte o log: agora "
                    "ele mostra o código real da autenticação e o resultado do LPR.",
                    "error",
                )
        self._diagnostic()

    def start_test_server_login(self) -> None:
        if not is_admin():
            messagebox.showerror(
                "PrintRescue",
                "Execute o aplicativo como administrador.",
            )
            return
        p = self.profile()
        if hostname().casefold() == p.server_name.casefold():
            messagebox.showinfo(
                "PrintRescue",
                "Este teste deve ser executado no computador cliente.",
            )
            return
        self.background(self._test_server_login)

    def _test_server_login(self) -> None:
        p = self.profile()
        rep = Repairs(self.storage, self.log)
        self.set_status("Testando credencial do servidor...")

        ok, message, code = rep.authenticate_saved(p)
        if ok:
            self.log("Teste concluído: credencial salva válida.", "ok")
            return

        password = self.ask_password_sync(
            f"Digite a senha de {p.server_name}\\{p.network_user}"
        )
        if not password:
            self.log("Teste cancelado.", "warn")
            return

        ok, message, code = rep.authenticate_with_password(p, password)
        password = None

        if ok:
            self.log(
                "Teste concluído: usuário, senha e conexão SMB estão corretos.",
                "ok",
            )
        else:
            self.log(
                f"Teste concluído com falha: {message} (código {code}).",
                "error",
            )

    def start_rebuild_client(self) -> None:
        if not is_admin():
            messagebox.showerror(
                "PrintRescue",
                "Execute o aplicativo como administrador.",
            )
            return
        p = self.profile()
        if hostname().casefold() == p.server_name.casefold():
            messagebox.showinfo(
                "PrintRescue",
                "No servidor, use 'Reparo automático seguro'. "
                "A reconstrução da fila é feita no computador cliente.",
            )
            return
        if not messagebox.askyesno(
            "PrintRescue",
            "O programa fará backup, removerá somente as filas conflitantes "
            "deste perfil e recriará a impressora usando o driver "
            f"'{p.expected_driver}'. Continuar?",
        ):
            return
        self.save_profile()
        self.background(self._rebuild_client)

    def _rebuild_client(self) -> None:
        p = self.profile()
        rep = Repairs(self.storage, self.log)
        rep.backup(p)
        self.set_status("Recriando a fila do cliente...")
        installed, reboot = rep.rebuild_client_queue_lpr(
            p,
            force_cleanup=True,
        )
        self.reboot_required = reboot
        if installed:
            self.log(
                "A fila conflitante foi removida e a impressora foi recriada.",
                "ok",
            )
        elif reboot:
            self.log(
                "O monitor LPR foi habilitado. Reinicie o cliente e clique "
                "novamente em 'Recriar fila do zero'.",
                "warn",
            )
            self.ask_reboot()
        else:
            self.log(
                "Não foi possível recriar. Confirme que a versão 4.2 foi "
                "executada no CF para ativar o servidor LPD.",
                "error",
            )
        self._diagnostic()

    def ask_password_sync(self, prompt: str, confirm: bool = False) -> str | None:
        holder = {"value": None}
        event = threading.Event()

        def dialog():
            first = simpledialog.askstring("PrintRescue", prompt, show="*", parent=self.root)
            if first is None:
                event.set()
                return
            if confirm:
                second = simpledialog.askstring(
                    "PrintRescue", "Digite a senha novamente:", show="*", parent=self.root
                )
                if first != second:
                    messagebox.showerror("PrintRescue", "As senhas não coincidem.")
                    event.set()
                    return
            holder["value"] = first
            event.set()

        self.root.after(0, dialog)
        event.wait()
        return holder["value"]

    def ask_reboot(self) -> None:
        def dialog():
            if messagebox.askyesno(
                "PrintRescue",
                "O Windows registrou a conexão, mas precisa reiniciar este PC. Reiniciar agora?",
            ):
                subprocess.Popen(["shutdown.exe", "/r", "/t", "10"])

        self.root.after(0, dialog)

    def detect_devices(self) -> None:
        def work():
            self.set_status("Detectando impressoras e drivers...")
            r = powershell(
                "$p=Get-Printer -ErrorAction SilentlyContinue | "
                "Select-Object Name,Type,DriverName,PortName,Shared,ShareName;"
                "$d=Get-PrinterDriver -ErrorAction SilentlyContinue | "
                "Select-Object Name,Manufacturer,MajorVersion,PrinterEnvironment;"
                "[pscustomobject]@{Printers=$p;Drivers=$d} | ConvertTo-Json -Depth 5"
            )
            text = r.stdout or r.stderr
            self.root.after(
                0,
                lambda: (
                    self.device_text.delete("1.0", "end"),
                    self.device_text.insert("1.0", text),
                ),
            )

        self.background(work)

    def import_inf(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione o driver .INF",
            filetypes=[("Driver INF", "*.inf")],
        )
        if not path:
            return
        self.background(
            lambda: Repairs(self.storage, self.log).import_driver_inf(
                path, self.expected_driver.get().strip()
            )
        )

    def list_drivers(self) -> None:
        def work():
            r = powershell(
                "Get-PrinterDriver -ErrorAction SilentlyContinue | "
                "Sort-Object Name | Format-Table Name,Manufacturer,"
                "MajorVersion,PrinterEnvironment -AutoSize | Out-String -Width 220"
            )
            self.root.after(
                0,
                lambda: (
                    self.driver_text.delete("1.0", "end"),
                    self.driver_text.insert("1.0", r.stdout or r.stderr),
                ),
            )

        self.background(work)

    def create_backup(self) -> None:
        self.background(lambda: Repairs(self.storage, self.log).backup(self.profile()))

    def restore_backup(self) -> None:
        folder = filedialog.askdirectory(
            title="Selecione a pasta do backup",
            initialdir=str(self.storage.backups),
        )
        if not folder:
            return
        if not messagebox.askyesno(
            "PrintRescue",
            "Restaurar as configurações de registro deste backup?",
        ):
            return
        self.background(
            lambda: Repairs(self.storage, self.log).restore_registry_backup(Path(folder))
        )

    def restart_spooler(self) -> None:
        self.background(
            lambda: self.log(
                "Spooler reiniciado."
                if powershell("Restart-Service Spooler -Force").ok
                else "Falha reiniciando Spooler.",
                "ok",
            )
        )

    def direct_tcp(self) -> None:
        if not messagebox.askyesno(
            "PrintRescue",
            "A impressora possui IP próprio e aceita impressão RAW/TCP? "
            "Não use este modo para uma impressora USB compartilhada por outro computador.",
        ):
            return
        self.background(
            lambda: Repairs(self.storage, self.log).direct_tcp_install(self.profile())
        )

    def print_test(self) -> None:
        p = self.profile()
        if hostname().casefold() == p.server_name.casefold():
            name = p.local_printer_name
        else:
            detect = powershell(
                f"$p=Get-Printer -Name "
                f"'{p.client_queue_name.replace(chr(39), chr(39)*2)}' "
                "-ErrorAction SilentlyContinue;"
                "if($p){$p.Name}else{exit 2}"
            )
            name = (
                detect.stdout.strip()
                if detect.ok
                else rf"\\{p.server_name}\{p.share_name}"
            )
        self.background(
            lambda: self.log(
                "Página de teste enviada."
                if subprocess.run(
                    [
                        str(Path(os.environ["WINDIR"]) / "System32" / "rundll32.exe"),
                        "printui.dll,PrintUIEntry",
                        "/k",
                        "/n",
                        name,
                    ],
                    creationflags=0x08000000,
                ).returncode
                == 0
                else "Falha ao enviar página de teste.",
                "ok",
            )
        )

    def export_report(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Salvar relatório",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Texto", "*.txt")],
            initialfile=f"PrintRescue_{hostname()}_{datetime.now():%Y%m%d_%H%M}.json",
        )
        if not path:
            return
        payload = {
            "version": __version__,
            "computer": hostname(),
            "profile": self.profile().to_dict(),
            "results": [x.to_dict() for x in self.last_results],
        }
        Path(path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.log(f"Relatório exportado: {path}", "ok")

    @staticmethod
    def open_printers() -> None:
        subprocess.Popen(["control.exe", "printers"])

    @staticmethod
    def open_device_manager() -> None:
        subprocess.Popen(["devmgmt.msc"])

    @staticmethod
    def open_credentials() -> None:
        subprocess.Popen(["control.exe", "/name", "Microsoft.CredentialManager"])

    @staticmethod
    def open_gpedit() -> None:
        try:
            subprocess.Popen(["gpedit.msc"])
        except OSError:
            messagebox.showinfo("PrintRescue", "O Editor de Política pode não existir no Windows Home.")

    @staticmethod
    def open_registry() -> None:
        subprocess.Popen(
            [
                "reg.exe",
                "add",
                r"HKCU\Software\Microsoft\Windows\CurrentVersion\Applets\Regedit",
                "/v",
                "LastKey",
                "/t",
                "REG_SZ",
                "/d",
                r"Computer\HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows NT\Printers",
                "/f",
            ],
            creationflags=0x08000000,
        ).wait()
        subprocess.Popen(["regedit.exe"])


def main() -> None:
    if os.name != "nt":
        raise SystemExit("PrintRescue funciona somente no Windows.")

    if not is_admin():
        if elevate_current_process():
            raise SystemExit

    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    PrintRescueApp(root)
    root.mainloop()
