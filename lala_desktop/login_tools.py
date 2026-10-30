"""Windows LaLa login. Legacy-server experiment is opt-in, never automatic.

Extracted server list and C63-7 protocol from original WLRe_lala.
Legacy XOR is reversible obfuscation, NOT protected transport. A successful
legacy reply is NOT proof of current official server identity or an audited
live game session. Credentials are never persisted or logged.
"""
import tkinter as tk
from tkinter import ttk
from queue import Empty, SimpleQueue
from threading import Thread

from lala_core.login import LoginCoordinator, LoginError, validate_credentials
from lala_core.legacy_login_trial import (
    LegacyLoginTrial, LegacyTrialResult, LegacyRoleTrialResult,
    LegacyReadOnlyObservation,
)
from lala_core.server_probe import LINE_SNAPSHOT, probe_line
from lala_core.resource_bootstrap import verify_installed, InstallError
from . import theme as t


def build_login_tool(parent, *, font_name, button_factory, adapter=None):
    coordinator = LoginCoordinator(adapter=adapter)
    parent._lala_login_coordinator = coordinator
    parent.winfo_toplevel()._lala_login_coordinator = coordinator
    status = tk.StringVar(master=parent, value="尚未登入。舊版分流可手動試驗，非正式服驗收。")
    role_info = tk.StringVar(master=parent, value="角色資料：尚未同步。")
    choices = {
        f"{name}（{line_id}）": line_id
        for line_id, (name, host, port) in LINE_SNAPSHOT.items()
    }
    area = tk.Frame(parent, bg=t.PANEL)
    area.pack(fill="x", padx=24, pady=(8, 2))
    area.columnconfigure(1, weight=1)
    area.columnconfigure(3, weight=1)

    def label(row, column, title):
        tk.Label(area, text=title, fg=t.TEXT, bg=t.PANEL,
                 font=(font_name, 10)).grid(
            row=row, column=column, sticky="w", padx=(0, 8), pady=4)

    label(0, 0, "分流")
    selected_line = tk.StringVar(master=parent, value=next(iter(choices)))
    ttk.Combobox(
        area, textvariable=selected_line, values=list(choices),
        state="readonly", width=27, font=(font_name, 10)).grid(
        row=0, column=1, columnspan=3, sticky="ew", pady=4)

    def make_entry(column, title, *, masked=False):
        label(1, column, title)
        field = tk.Entry(area, font=(font_name, 11), bg=t.FIELD, fg=t.TEXT,
                         insertbackground=t.TEXT, bd=0, highlightthickness=1,
                         highlightbackground=t.BORDER,
                         show="●" if masked else "")
        field.grid(row=1, column=column + 1, sticky="ew",
                   padx=(0, 14), pady=4)
        return field

    account = make_entry(0, "帳號")
    password = make_entry(2, "密碼", masked=True)
    role_name = tk.StringVar(master=parent, value="")
    label(2, 0, "角色")
    role_picker = ttk.Combobox(
        area, textvariable=role_name, values=(),
        state="disabled", font=(font_name, 10))
    role_picker.grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)

    allow_legacy = tk.BooleanVar(master=parent, value=False)
    readonly_observe = tk.BooleanVar(master=parent, value=False)
    consent_row = tk.Frame(parent, bg=t.PANEL)
    consent_row.pack(fill="x", padx=24, pady=(0, 2))
    tk.Checkbutton(
        consent_row, variable=allow_legacy,
        text="我了解舊版 XOR 非加密，並同意本次向舊版分流 IP 傳送帳密",
        bg=t.PANEL, fg=t.WARN, activebackground=t.PANEL,
        activeforeground=t.TEXT, selectcolor=t.FIELD,
        font=(font_name, 9), anchor="w").pack(side="left")
    tk.Checkbutton(
        consent_row, variable=readonly_observe,
        text="選角後唯讀觀測 60 秒",
        bg=t.PANEL, fg=t.CYAN, activebackground=t.PANEL,
        activeforeground=t.TEXT, selectcolor=t.FIELD,
        font=(font_name, 9), anchor="w").pack(side="right")

    actions = tk.Frame(parent, bg=t.PANEL)
    actions.pack(fill="x", padx=24, pady=(4, 2))
    events = SimpleQueue()
    state = {"tcp": False, "login": False, "role": False,
             "generation": 0, "client": None, "slots": (), "after": None}

    def update():
        if not parent.winfo_exists():
            return
        try:
            while True:
                kind, generation, result, message = events.get_nowait()
                if kind == "tcp":
                    state["tcp"] = False
                    tcp_button.set_enabled(True)
                    status.set(message)
                elif generation != state["generation"]:
                    # Old worker must not revive disconnected login.
                    continue
                elif kind == "login":
                    state["login"] = False
                    login_button.set_enabled(True)
                    if isinstance(result, LegacyTrialResult):
                        role_info.set("已取得舊版角色槽位：" +
                                      "、".join(str(x) for x in result.role_slots) +
                                      "。等待選角後的 S3-1 角色資料。")
                        state["slots"] = result.role_slots
                        role_picker.configure(
                            values=tuple(str(x) for x in result.role_slots),
                            state="readonly")
                        role_name.set(str(result.role_slots[0]))
                        status.set("舊版帳號驗證／正式登入皆收到成功回覆，"
                                   "已取得角色槽位；尚未獨立證實目前官方伺服器身分。")
                    else:
                        state["slots"] = ()
                        role_info.set("角色資料：未取得，舊版登入未成功。")
                        status.set(message)
                elif kind == "role":
                    state["role"] = bool(
                        isinstance(result, LegacyRoleTrialResult)
                        and result.ongoing_connection)
                    if isinstance(result, LegacyRoleTrialResult):
                        if not result.ongoing_connection:
                            state["client"] = None
                        state["slots"] = ()
                        role_picker.configure(values=(), state="disabled")
                        role_info.set(
                            f"已解析角色：{result.character_name}（角色 ID {result.role_id}）"
                            f"｜場景 {result.scene}｜座標 {result.x}, {result.y}。")
                        acknowledgement = (
                            "已依舊版送出 C12-1／C3-2 初始化回覆；"
                            if result.init_acks_sent else
                            "尚未證實已送出世界初始化回覆；")
                        connection_note = (
                            "正在進行 60 秒唯讀觀測；只允許舊版心跳回覆。"
                            if result.ongoing_connection else
                            "試驗連線已關閉。")
                        status.set("S3-1 角色資料完整解析，S1-11 初始化確認已收到；"
                                   + acknowledgement + connection_note
                                   + "仍非可信正式服會話。")
                    else:
                        # select_role() closes the trial socket even on failure.
                        # Do not leave stale slots selectable as if still online.
                        state["client"] = None
                        state["slots"] = ()
                        role_name.set("")
                        role_picker.configure(values=(), state="disabled")
                        role_info.set("角色資料：未完成，請查看上方訊息。")
                        status.set(message)
                elif kind == "observation":
                    state["role"] = False
                    state["client"] = None
                    if isinstance(result, LegacyReadOnlyObservation):
                        status.set(
                            f"60 秒唯讀觀測完成：觀察到 {result.packets_seen} 個"
                            f"非心跳封包、回覆 {result.heartbeat_replies} 次心跳；"
                            "試驗連線已關閉。仍不代表正式登入。")
                    else:
                        status.set("限時唯讀觀測中止並關閉連線：" + message)
        except Empty:
            pass
        state["after"] = parent.after(100, update)

    def test_connection():
        if state["tcp"]:
            return
        line = choices.get(selected_line.get())
        if line is None:
            status.set("請選擇舊版分流")
            return
        state["tcp"] = True
        tcp_button.set_enabled(False)
        status.set("只測試 TCP 連線，不傳送帳號或密碼。")

        def task():
            try:
                result = probe_line(line, timeout=3)
                message = ("TCP 可連線，但不代表登入成功／分流身分已驗證。"
                           if result.tcp_reachable else
                           "TCP 未連線：" + result.status)
            except Exception:
                message = "TCP 測試失敗（未送出登入資料）"
            events.put(("tcp", 0, None, message))

        Thread(target=task, daemon=True, name="lala-login-tcp").start()

    def request_login():
        if state["login"] or state["role"]:
            return
        secret = password.get()
        password.delete(0, "end")
        try:
            verify_installed()
        except (InstallError, OSError):
            status.set("LaLa 必要官方資源尚未安裝完成；請重新執行 run_lala.bat")
            return
        line = choices.get(selected_line.get())
        if not allow_legacy.get():
            try:
                coordinator.begin(line_id=line, account=account.get(),
                                  password=secret, resources_verified=True)
            except LoginError:
                pass
            status.set("預設禁止傳送密碼；實驗舊版登入需先自行勾選 XOR 風險同意。")
            return
        try:
            validate_credentials(account.get(), secret)
            if type(line) is not int or line not in LINE_SNAPSHOT:
                raise LoginError("請選擇舊版已記錄的分流")
        except LoginError as error:
            status.set(str(error))
            return

        # Authorization is for exactly this click. A subsequent attempt,
        # account change or retry requires the user to opt in again.
        allow_legacy.set(False)
        coordinator.cancel()  # never elevate legacy results into trusted session
        if state["client"] is not None:
            state["client"].close()
        client = LegacyLoginTrial()
        state["generation"] += 1
        generation = state["generation"]
        state["client"], state["slots"] = client, ()
        role_name.set("")
        role_info.set("角色資料：正在驗證，尚未取得。")
        role_picker.configure(state="disabled", values=())
        state["login"] = True
        login_button.set_enabled(False)
        status.set("已同意以 XOR 傳送本次登入資料；正在執行舊版驗證／正式登入……")

        def task(once_secret=secret, once_account=account.get(),
                 once_line=line, once_client=client, once_generation=generation):
            try:
                result = once_client.authenticate(
                    line_id=once_line, account=once_account,
                    password=once_secret, consent=True)
                message = ""
            except LoginError as error:
                result, message = None, str(error)
            except Exception:
                result, message = None, "登入試驗未完成；不輸出伺服器原始回應"
            events.put(("login", once_generation, result, message))

        Thread(target=task, daemon=True, name="lala-login-trial").start()

    def disconnect():
        state["generation"] += 1
        state["login"] = state["role"] = False
        login_button.set_enabled(True)
        if state["client"] is not None:
            state["client"].close()
            state["client"] = None
        state["slots"] = ()
        coordinator.cancel()
        role_name.set("")
        role_info.set("角色資料：已中斷，清除先前的角色資訊。")
        role_picker.configure(state="disabled", values=())
        password.delete(0, "end")
        allow_legacy.set(False)
        readonly_observe.set(False)
        status.set("已關閉試驗連線並清除角色／會話狀態。")

    parent.winfo_toplevel()._lala_login_disconnect = disconnect

    def choose_role():
        try:
            slot = int(role_name.get())
        except ValueError:
            status.set("尚未取得伺服器角色清單")
            return
        client = state["client"]
        if state["login"] or state["role"]:
            return
        if client is None or slot not in state["slots"]:
            status.set("沒有有效的舊版登入連線，無法送出角色選擇")
            return
        observe = readonly_observe.get()
        readonly_observe.set(False)  # explicit per-role opt-in
        state["role"] = True
        generation = state["generation"]
        status.set("正在執行舊版選角試驗；不會啟動自動操作。")

        def task():
            try:
                # Preserve the original 1-argument call when observation is off.
                result = (client.select_role(slot, keep_open=True) if observe
                          else client.select_role(slot))
            except LoginError as error:
                events.put(("role", generation, None, str(error)))
                return
            except Exception:
                events.put(("role", generation, None, "選角試驗未完成"))
                return
            events.put(("role", generation, result, ""))
            if observe and result.ongoing_connection:
                try:
                    summary = client.observe_readonly(duration=60)
                    events.put(("observation", generation, summary, ""))
                except LoginError as error:
                    events.put(("observation", generation, None, str(error)))
                except Exception:
                    client.close()
                    events.put(("observation", generation, None,
                                "試驗已停止（不顯示私有封包或例外內容）"))

        Thread(target=task, daemon=True, name="lala-role-trial").start()

    login_button = button_factory(actions, "登入", request_login)
    login_button.pack(side="left", padx=(0, 8))
    button_factory(actions, "中斷", disconnect).pack(side="left", padx=(0, 8))
    tcp_button = button_factory(actions, "測試 TCP", test_connection)
    tcp_button.pack(side="left", padx=(0, 8))
    button_factory(actions, "選擇角色", choose_role).pack(side="right")

    tk.Label(parent, textvariable=status, font=(font_name, 10),
             fg=t.CYAN, bg=t.PANEL, wraplength=660, justify="left",
             anchor="w").pack(fill="x", padx=24, pady=(7, 2))
    tk.Label(parent, textvariable=role_info, font=(font_name, 10),
             fg=t.TEXT, bg=t.PANEL, wraplength=660, justify="left",
             anchor="w").pack(fill="x", padx=24, pady=(0, 4))
    tk.Label(parent,
             text="分流來源：舊版 server_list.json。XOR 非保密通道；"
                  "手動登入成功僅表示舊協定回覆，無正式服身分保證。",
             font=(font_name, 9), fg=t.WARN, bg=t.PANEL,
             wraplength=660, justify="left").pack(fill="x", padx=24)

    def cleanup(event):
        if event.widget is parent:
            state["generation"] += 1
            coordinator.cancel()
            if state["client"] is not None:
                state["client"].close()
            if state["after"] is not None:
                try:
                    parent.after_cancel(state["after"])
                except tk.TclError:
                    pass
                state["after"] = None

    parent.bind("<Destroy>", cleanup, add="+")
    state["after"] = parent.after(100, update)
    return True
