"""使用者明確要求後，只做一次遊戲分流 TCP connect/close。

伺服器位址取自舊版 WLRe_lala/wlre/resources/server_list.json
在 P1 開發時的檔案快照；**不代表這些位址目前仍是官方最新分流**。
僅驗證 TCP 路徑，不發登入、心跳、遊戲協定封包，不接收任何內容。
"""
from dataclasses import asdict, dataclass
import argparse
import json
import socket
import time


# 舊版已記錄的分流快照；使用固定白名單，禁止使用者輸入任意掃描目標。
# 若官方日後更新分流，必須從已核對的新來源更新此表與版本證據。
_LINES = (
    (101, "地球召引 1 線", "34.81.10.22", 16988),
    (102, "地球召引 2 線", "35.194.144.7", 16988),
    (103, "地球召引 3 線", "104.155.198.206", 16988),
    (104, "地球召引 4 線", "35.236.157.85", 16988),
    (105, "地球召引 5 線", "35.201.137.25", 16988),
    (201, "水星躍動 1 線", "34.81.92.114", 16988),
    (202, "水星躍動 2 線", "104.155.199.27", 16988),
)
LINE_SNAPSHOT = {line: (name, host, port) for line, name, host, port in _LINES}


@dataclass(frozen=True, slots=True)
class ProbeResult:
    line_id: int
    line_name: str
    endpoint: str
    status: str
    tcp_reachable: bool
    elapsed_ms: int
    transmitted_bytes: int = 0
    authenticated: bool = False
    protocol_compatible: bool = False

    def to_dict(self):
        return asdict(self)


def probe_line(line_id: int = 101, *, timeout: float = 3.0, connector=None,
               clock=None) -> ProbeResult:
    """單次 TCP connect；不用 send/recv，不重試，不持久化任何資訊。

    成功只代表 socket 層建立連線；對方是否仍為官方遊戲伺服器未證實。
    """
    if type(line_id) is not int or line_id not in LINE_SNAPSHOT:
        raise ValueError("必須選擇舊版已核對的伺服器分流 ID")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 5:
        raise ValueError("TCP 連線逾時需介於 0 與 5 秒")
    name, host, port = LINE_SNAPSHOT[line_id]
    connector = socket.create_connection if connector is None else connector
    clock = time.monotonic if clock is None else clock
    started = clock()
    status, success = "network_error", False
    try:
        # 開啟後立即關閉；無任何應用層資料，避免登入、重送、操作副作用。
        with connector((host, port), timeout=timeout):
            status, success = "tcp_connected", True
    except ConnectionRefusedError:
        status = "connection_refused"
    except (socket.timeout, TimeoutError):
        status = "timeout"
    except socket.gaierror:
        status = "dns_error"
    except OSError:
        status = "network_error"
    elapsed = min(60000, max(0, int((clock() - started) * 1000)))
    return ProbeResult(line_id, name, f"{host}:{port}", status, success, elapsed)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LaLa 官方分流舊版快照：單次無封包 TCP 連線檢查")
    parser.add_argument("--online", action="store_true",
                        help="明確允許這次 TCP connect/close")
    parser.add_argument("--line", type=int, default=101,
                        help="舊版分流 ID，預設 101 地球召引 1 線")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.online:
        parser.error("請明確加上 --online 才會建立 TCP 連線")
    try:
        result = probe_line(args.line, timeout=args.timeout)
    except ValueError as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"分流：{result.line_name}（舊版快照：{result.endpoint}）")
        print(f"TCP 狀態：{result.status}；耗時 {result.elapsed_ms}ms")
        print("已發送遊戲資料：0 bytes；登入：否；協定驗證：否")
    return 0 if result.tcp_reachable else 1


if __name__ == "__main__":
    raise SystemExit(main())
