"""Windows LaLa account/login screen, separate from generic offline tools.

Never store or print the password. A real authentication request is impossible
until an audited adapter verifies the current official endpoint and protocol.
A manual TCP probe is allowed but must never be labelled as authenticated.
"""
import tkinter as tk
from tkinter import ttk
from queue import Empty, SimpleQueue
from threading import Thread

from lala_core.login import LoginCoordinator, LoginError
from lala_core.server_probe import LINE_SNAPSHOT, probe_line
from lala_core.resource_bootstrap import verify_installed, InstallError
from . import theme as t


def build_login_tool(parent, *, font_name, button_factory, adapter=None):
    coordinator = LoginCoordinator(adapter=adapter)
    parent._lala_login_coordinator = coordinator
    parent.winfo_toplevel()._lala_login_coordinator = coordinator
    status = tk.StringVar(master=parent, value="尚未登入。正式服身分及協定尚未驗證。")
    choices = {
        f"{name}（{line_id}）": line_id
        for line_id, (name, host, port) in LINE_SNAPSHOT.items()
    }
    area = tk.Frame(parent, bg=t.PANEL)
    area.pack(fill="x", padx=24, pady=(10, 2))
    area.columnconfigure(1, weight=1)
    area.columnconfigure(3, weight=1)

    def label(row, column, title):
        tk.Label(area, text=title, fg=t.TEXT, bg=t.PANEL,
                 font=(font_name, 10)).grid(
                     row=row, column=column, sticky="w", padx=(0, 8), pady=5)

    label(0, 0, "官方分流")
    line_choice = tk.StringVar(master=parent, value=next(iter(choices)))
    selector = ttk.Combobox(
        area, textvariable=line_choice, values=list(choices),
        state="readonly", width=27, font=(font_name, 10))
    selector.grid(row=0, column=1, columnspan=3, sticky="ew", pady=5)

    def entry_field(column, title, *, masked=False):
        label(1, column, title)
        field = tk.Entry(area, font=(font_name, 11), bg=t.FIELD, fg=t.TEXT,
                         insertbackground=t.TEXT, bd=0,
                         highlightthickness=1, highlightbackground=t.BORDER,
                         show="●" if masked else "")
        field.grid(row=1, column=column + 1, sticky="ew", padx=(0, 14), pady=5)
        return field

    account = entry_field(0, "帳號")
    password = entry_field(2, "密碼", masked=True)

    roles = tk.StringVar(master=parent, value="")
    tk.Label(area, text="角色", font=(font_name, 10), fg=t.TEXT,
             bg=t.PANEL).grid(row=2, column=0, sticky="w", pady=5)
    role_picker = ttk.Combobox(area, textvariable=roles,
                               values=(), state="disabled",
                               font=(font_name, 10))
    role_picker.grid(row=2, column=1, columnspan=3, sticky="ew", pady=5)

    actions = tk.Frame(parent, bg=t.PANEL)
    actions.pack(fill="x", padx=24, pady=(9, 3))
    messages = SimpleQueue()
    state = {"tcp": False, "login": False}
    scheduled = {"after_id": None}

    def refresh():
        if not parent.winfo_exists():
            return
        try:
            while True:
                kind, data = messages.get_nowait()
                if kind == "tcp":
                    state["tcp"] = False
                    tcp_button.set_enabled(True)
                    status.set(data)
                elif kind == "auth":
                    state["login"] = False
                    login_button.set_enabled(True)
                    generation, outcome = data
                    ok = coordinator.complete(generation, outcome)
                    view = coordinator.view()
                    if ok:
                        names = tuple(str(x) for x in view.role_slots)
                        role_picker.configure(values=names, state="readonly" if names else "disabled")
                        if names:
                            roles.set(names[0])
                        status.set("已收到經驗證登入回覆，請等待角色協定驗收。")
                    elif generation == view.generation:
                        status.set(view.reason)
        except Empty:
            pass
        scheduled["after_id"] = parent.after(100, refresh)

    def test_connection():
        if state["tcp"]:
            return
        line = choices.get(line_choice.get())
        if line is None:
            status.set("請先選擇已核對的分流")
            return
        state["tcp"] = True
        tcp_button.set_enabled(False)
        status.set("正在測試 TCP 可達性，不會傳送帳號或密碼。")

        def task():
            try:
                result = probe_line(line, timeout=3)
                message = (
                    "TCP 可連線，但不代表已驗證官方分流或成功登入。"
                    if result.tcp_reachable else
                    "無法建立 TCP：" + result.status + "；不能推定帳號驗證結果。"
                )
            except Exception:
                message = "TCP 測試無法完成；請確認分流與網路。"
            messages.put(("tcp", message))

        Thread(target=task, daemon=True, name="lala-login-tcp-test").start()

    def request_login():
        if state["login"]:
            return
        # Delete password entry immediately; never keep it in Tk after click.
        secret = password.get()
        password.delete(0, "end")
        try:
            verify_installed()
            resources_ready = True
        except (InstallError, OSError):
            resources_ready = False
        try:
            line = choices.get(line_choice.get())
            generation = coordinator.begin(
                line_id=line, account=account.get(),
                password=secret, resources_verified=resources_ready)
        except LoginError as error:
            status.set(str(error))
            return
        finally:
            # Cannot guarantee zeroization of immutable Python str; do not log,
            # cache, retry or serialize. Drop the reference after the worker.
            pass
        state["login"] = True
        login_button.set_enabled(False)
        status.set("正在等待已核對的伺服器驗證回覆……")

        def task(once_secret=secret, once_account=account.get(), once_generation=generation):
            try:
                result = coordinator.authenticate(generation=once_generation,
                                                  account=once_account, password=once_secret)
            except Exception:
                result = None  # no raw server exception/credentials in UI
            messages.put(("auth", (once_generation, result)))

        Thread(target=task, daemon=True, name="lala-login-authorized-only").start()

    def disconnect():
        coordinator.cancel()
        password.delete(0, "end")
        roles.set("")
        role_picker.configure(values=(), state="disabled")
        status.set("已中斷；清除登入會話與角色狀態。")

    parent.winfo_toplevel()._lala_login_disconnect = disconnect

    def choose_role():
        try:
            selection = int(roles.get())
        except ValueError:
            status.set("請先等待正式登入成功及角色清單。")
            return
        if not coordinator.choose_role(role_id=selection):
            status.set(coordinator.view().reason)

    login_button = button_factory(actions, "登入", request_login)
    login_button.pack(side="left", padx=(0, 8))
    button_factory(actions, "中斷", disconnect).pack(side="left", padx=(0, 8))
    tcp_button = button_factory(actions, "測試 TCP", test_connection)
    tcp_button.pack(side="left", padx=(0, 8))
    button_factory(actions, "選擇角色", choose_role).pack(side="right")

    tk.Label(parent, textvariable=status, font=(font_name, 10), fg=t.CYAN,
             bg=t.PANEL, wraplength=650, justify="left",
             anchor="w").pack(fill="x", padx=24, pady=(8, 3))
    tk.Label(parent,
             text="密碼不會儲存。舊版登入封包僅 XOR 混淆，未驗證現行正式服協定時絕不送出密碼。",
             font=(font_name, 9), fg=t.WARN, bg=t.PANEL, wraplength=660,
             justify="left").pack(fill="x", padx=24, pady=(0, 4))

    def cleanup(event):
        if event.widget is parent:
            coordinator.cancel()
            after_id = scheduled["after_id"]
            scheduled["after_id"] = None
            if after_id is not None:
                try:
                    parent.after_cancel(after_id)
                except tk.TclError:
                    pass

    parent.bind("<Destroy>", cleanup, add="+")
    scheduled["after_id"] = parent.after(100, refresh)
    return True
