"""P1 本機可操作工具視窗，永不讀取/送出遊戲封包。

由主視窗的功能按鈕開啟，只有使用者自行填寫資料才進行離線計算。
"""
import tkinter as tk
from queue import Empty, SimpleQueue
from threading import Thread
from lala_core.resource_inspector import inspect
from lala_core.official_versions import OfficialVersionError
from . import theme as t
from lala_core.efficiency import ExperienceSample, estimate_experience
from lala_core.planning import (
    MaterialRequirement, plan_crafting, ExpeditionMember, plan_expedition,
)
from lala_core.feature_progress import PROGRESS


def parse_pairs(text):
    """材料輸入格式：物品ID:數量,物品ID:數量（同物品 ID 會累計）。"""
    output = {}
    for segment in text.split(","):
        segment = segment.strip()
        if not segment:
            continue
        pair = segment.split(":")
        if len(pair) != 2:
            raise ValueError("請使用 ID:數量，以逗號分隔")
        key, count = (int(x.strip()) for x in pair)
        if key <= 0 or count < 0:
            raise ValueError("ID 必須大於 0，數量不可小於 0")
        output[key] = output.get(key, 0) + count
    return output


def build_local_tool(parent, key, *, font_name, button_factory):
    """True：有實際可操作工具；官方資源查詢僅在使用者按鈕後唯讀執行。"""
    if key == "resources":
        return _build_resource_inspector(parent, font_name=font_name,
                                         button_factory=button_factory)
    if key not in ("efficiency", "crafting", "inventory", "expeditions"):
        return False

    status = tk.StringVar(value="離線工具：手動輸入資料，不會發送任何遊戲指令。")
    area = tk.Frame(parent, bg=t.PANEL)
    area.pack(fill="x", padx=24, pady=(6, 0))

    def input_row(row, label, default=""):
        tk.Label(area, text=label, font=(font_name, 10), fg=t.TEXT, bg=t.PANEL).grid(
            row=row, column=0, sticky="w", pady=4)
        item = tk.Entry(area, bg=t.FIELD, fg=t.TEXT, insertbackground=t.TEXT, bd=0,
                        highlightthickness=1, highlightbackground=t.BORDER,
                        font=(font_name, 11))
        item.insert(0, default)
        item.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        return item

    area.columnconfigure(1, weight=1)
    if key == "efficiency":
        start_exp = input_row(0, "起始經驗")
        finish_exp = input_row(1, "目前經驗")
        duration = input_row(2, "經過秒數")
        goal = input_row(3, "目標總經驗（可空白）")

        def calc():
            result = estimate_experience(
                ExperienceSample(0, int(start_exp.get())),
                ExperienceSample(float(duration.get()), int(finish_exp.get())),
                int(goal.get()) if goal.get().strip() else None,
            )
            eta = "無法估計" if result.hours_to_target is None else f"{result.hours_to_target:.2f} 小時"
            return f"每小時 {result.experience_per_hour:.1f} EXP；剩餘時間：{eta}"

    elif key in ("crafting", "inventory"):
        recipe = input_row(0, "配方 ID")
        quantity = input_row(1, "製作數量")
        materials = input_row(2, "材料（ID:份量,...）")
        owned = input_row(3, "持有（ID:數量,...）")
        reserved = input_row(4, "預約（選填）")

        def calc():
            req = [MaterialRequirement(k, v) for k, v in parse_pairs(materials.get()).items()]
            result = plan_crafting(int(recipe.get()), int(quantity.get()), req,
                                   parse_pairs(owned.get()), parse_pairs(reserved.get()))
            if not result.can_start:
                details = "、".join(f"#{v.item_id} 缺 {v.quantity}" for v in result.missing)
                return "材料不足：" + details
            return "手動填寫的材料條件符合；未啟動任何製作。"

    else:
        members = input_row(0, "夥伴 ID:體力:可派遣(1/0),...")
        selected = input_row(1, "選擇夥伴 ID（逗號分隔）")
        needed = input_row(2, "每隊人數")
        stamina = input_row(3, "最低體力")

        def calc():
            candidates = []
            for chunk in members.get().split(","):
                if not chunk.strip():
                    continue
                parts = [p.strip() for p in chunk.split(":")]
                if len(parts) != 3 or parts[2] not in ("0", "1"):
                    raise ValueError("夥伴格式為 ID:體力:可派遣(1/0)")
                candidates.append(ExpeditionMember(int(parts[0]), int(parts[1]),
                                                   parts[2] == "1"))
            selection = [int(x.strip()) for x in selected.get().split(",") if x.strip()]
            plan = plan_expedition(candidates, selection,
                                   minimum_stamina=int(stamina.get()),
                                   party_size=int(needed.get()))
            return "本機條件通過（尚未派遣）" if plan.accepted else plan.reason

    def run():
        try:
            status.set(calc())
        except (ValueError, OverflowError) as error:
            status.set("輸入有誤：" + str(error))

    button_factory(area, "本機計算", run).grid(
        row=6, column=1, sticky="e", padx=8, pady=(8, 0))
    tk.Label(parent, textvariable=status, fg=t.CYAN, bg=t.PANEL,
             font=(font_name, 10), wraplength=540, justify="left",
             anchor="w").pack(fill="x", padx=24, pady=(8, 4))
    return True


def _build_resource_inspector(parent, *, font_name, button_factory):
    """按下後才允許官方唯讀 GET；背景執行與 Tk 主線程分離。"""
    state = {"running": False}
    results = SimpleQueue()
    status = tk.StringVar(master=parent, value="尚未查詢。官方資料檢查不等於可以登入。")
    area = tk.Frame(parent, bg=t.PANEL)
    area.pack(fill="x", padx=24, pady=(8, 6))

    def poll_result():
        if not parent.winfo_exists():
            return
        try:
            message = results.get_nowait()
        except Empty:
            parent.after(80, poll_result)
            return
        state["running"] = False
        for control in controls:
            control.set_enabled(True)
        status.set(message)

    def request(manifests):
        if state["running"]:
            return
        state["running"] = True
        status.set("讀取官方公開資料中；不會登入遊戲或傳送操作指令…")
        for control in controls:
            control.set_enabled(False)

        def worker():
            try:
                report = inspect(with_manifests=manifests)
                text = (
                    f"ExeVer {report['exe_version']}；DataVer {report['data_version']}。"
                    f"{'兩份 Manifest 傳輸完整性通過。' if manifests else '僅取得版本資訊。'}"
                    " 尚未驗證資源解碼與正式服登入。"
                )
            except OfficialVersionError as error:
                text = "官方資源檢查失敗：" + str(error) + "；登入保持停用。"
            except Exception:
                # 對 UI 不暴露可能包含 URL、代理資訊與個資的底層 traceback。
                text = "資源檢查遇到未預期錯誤；登入保持停用。"
            results.put(text)

        Thread(target=worker, daemon=True, name="lala-official-readonly-check").start()
        parent.after(80, poll_result)

    controls = [
        button_factory(area, "查詢官方版本", lambda: request(False)),
        button_factory(area, "驗證兩包 Manifest", lambda: request(True)),
    ]
    for control in controls:
        control.pack(side="left", padx=(0, 8))
    tk.Label(parent, textvariable=status, fg=t.CYAN, bg=t.PANEL,
             font=(font_name, 10), wraplength=540, justify="left",
             anchor="w").pack(fill="x", padx=24, pady=(8, 4))
    tk.Label(parent, text="此功能僅使用官方公開 HTTPS 版本及 Manifest，不需帳密。"
                          "不下載遊戲 Bundle、不寫入安裝目錄。",
             fg=t.MUTED, bg=t.PANEL, font=(font_name, 10),
             wraplength=540, justify="left").pack(fill="x", padx=24)
    return True


def description(key):
    return PROGRESS[key].local_capability
