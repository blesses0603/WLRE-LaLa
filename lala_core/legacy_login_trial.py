"""EXPERIMENTAL login against endpoints extracted from legacy LaLa's server list.

Legacy PCAP-derived XOR C63-7 is NOT TLS encryption or current official
identity verification. Absolutely no traffic unless UI user opts in after
reading the warning. Never log, store, retry or include credentials in errors.
The result is *legacy protocol evidence*, not a production SessionStore login.
"""
from dataclasses import dataclass
from threading import RLock, Event
import socket
import time

from .login import LoginError, validate_credentials
from .login_wire import (
    build_legacy_request, decode_legacy_reply, parse_legacy_role_slots,
    decoder_for_legacy_fixture, OLD_TX_XOR, build_legacy_world_init_acks,
)
from .server_probe import LINE_SNAPSHOT
from .wire import WireDecodeError
from .legacy_world import parse_legacy_world_player


MAX_TRIAL_PACKETS = 512
# The old client capture includes 1,848 inbound packets over its full session.
# Selected-role bootstrap may exceed the 512-packet login-stage budget.
MAX_ROLE_PACKETS = 4096
MAX_ROLE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LegacyTrialResult:
    verification_accepted: bool
    formal_accepted: bool
    role_slots: tuple[int, ...]
    official_identity_verified: bool = False
    current_protocol_certified: bool = False


@dataclass(frozen=True, slots=True)
class LegacyRoleTrialResult:
    role_slot: int
    world_packet_observed: bool
    official_identity_verified: bool = False
    initial_data_complete: bool = False
    role_id: int | None = None
    character_name: str = ""
    scene: int | None = None
    x: int | None = None
    y: int | None = None
    schema: str = "legacy-1262"
    ongoing_connection: bool = False
    init_acks_sent: bool = False


def _small_frame(main, sub, payload=b""):
    import struct
    plain = b"\xc4\xc6" + struct.pack("<H", len(payload) + 2) + bytes((main, sub)) + payload
    return bytes(x ^ OLD_TX_XOR for x in plain)


class LegacyLoginTrial:
    """One manual verification connection, then one formal connection.

    Network authority is restricted to exactly the old server-list IPs. A
    successful packet exchange is evidence of legacy protocol interoperability
    only; it does NOT independently establish server authenticity.
    """
    def __init__(self, *, connector=None, monotonic=None, timeout=8):
        if type(timeout) not in (int, float) or not 1 <= timeout <= 15:
            raise LoginError("登入試驗逾時範圍必須為 1～15 秒")
        self._connect = connector if connector is not None else socket.create_connection
        self._clock = monotonic if monotonic is not None else time.monotonic
        self._timeout = timeout
        self._lock = RLock()
        self._stopped = Event()
        self._socket = None
        self._verified_slots = ()
        self._endpoint = None
        self._attempted = False
        self._formal_decoder = None  # retain partial frames across role-list and selection

    def close(self):
        self._stopped.set()
        with self._lock:
            connection, self._socket = self._socket, None
            self._verified_slots = ()
            self._endpoint = None
            self._formal_decoder = None
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass

    def _dial(self, endpoint):
        try:
            connection = self._connect(endpoint, timeout=min(self._timeout, 5))
            connection.settimeout(.25)
            return connection
        except OSError as error:
            raise LoginError("無法連接舊版分流位址；請檢查分流與網路") from None

    def _wait_packets(self, connection, decoder, deadline, *, phase):
        packets_seen = 0
        bytes_seen = 0
        limit = MAX_ROLE_PACKETS if phase == "選角" else MAX_TRIAL_PACKETS
        saw_world_player = False
        saw_initial_data_complete = False
        while not self._stopped.is_set() and self._clock() < deadline:
            try:
                data = connection.recv(8192)
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                raise LoginError("登入期間 TCP 連線中斷") from None
            if not data:
                raise LoginError("伺服器在完成舊版登入協定前關閉連線")
            bytes_seen += len(data)
            if phase == "選角" and bytes_seen > MAX_ROLE_BYTES:
                raise LoginError("舊版選角接收資料超過 8 MiB 安全上限，停止試驗")
            try:
                packets = decoder.feed(data)
            except WireDecodeError:
                raise LoginError("收到不同於舊版的封包格式；停止登入試驗") from None
            for packet in packets:
                packets_seen += 1
                key = (packet.main, packet.sub)
                saw_world_player |= key == (3, 1)
                saw_initial_data_complete |= key == (1, 11)
                if packets_seen > limit:
                    if phase == "選角":
                        # Only report whitelisted packet types, never payloads,
                        # role details, account data, or arbitrary server text.
                        world = "已收到" if saw_world_player else "未收到"
                        ready = "已收到" if saw_initial_data_complete else "未收到"
                        raise LoginError(
                            f"舊版選角試驗超過 {limit} 個封包；"
                            f"S3-1：{world}、S1-11：{ready}。"
                            "角色同步未完成，已停止試驗。")
                    raise LoginError(
                        f"舊版{phase}試驗超過 {limit} 個封包；"
                        "已停止試驗，不能判定登入成功。")
                if key == (1, 23):
                    if packet.payload:
                        raise LoginError("舊版 S1-23 心跳要求格式不符，停止試驗")
                    try:
                        connection.sendall(_small_frame(63, 5))
                    except OSError:
                        raise LoginError("舊版心跳回覆送出失敗") from None
                    continue
                yield packet
        if self._stopped.is_set():
            raise LoginError("已中斷登入試驗")
        raise LoginError("舊版登入回覆逾時；未確認目前協定")

    def _reply_phase(self, connection, *, kind, deadline,
                     need_roles=False, decoder=None):
        decoder = decoder if decoder is not None else decoder_for_legacy_fixture()
        accepted, slots = False, ()
        phase = "帳號驗證" if kind == 0 else "正式登入"
        for packet in self._wait_packets(connection, decoder, deadline, phase=phase):
            key = (packet.main, packet.sub)
            if key == (63, 7):
                try:
                    reply = decode_legacy_reply(packet, expected_kind=kind)
                except WireDecodeError:
                    raise LoginError("登入回覆種類／格式不符合舊版規格") from None
                if not reply.accepted:
                    raise LoginError("伺服器拒絕舊版登入請求（代碼：" +
                                     str(reply.result) + "）")
                accepted = True
                if not need_roles:
                    return ()
                if slots:
                    return slots
            elif key == (63, 1) and need_roles:
                try:
                    slots = parse_legacy_role_slots(packet)
                except WireDecodeError:
                    raise LoginError("角色清單格式與舊版不同；停止登入試驗") from None
                if accepted and slots:
                    return slots
            # Other packets, including possible echo of account/password
            # S1-4, are discarded without printing, retaining or parsing.
        raise LoginError("舊版登入缺少伺服器確認")

    def authenticate(self, *, line_id, account, password, consent=False
                     ) -> LegacyTrialResult:
        if consent is not True:
            raise LoginError("必須先勾選舊版 XOR 登入風險確認")
        validate_credentials(account, password)
        if type(line_id) is not int or line_id not in LINE_SNAPSHOT:
            raise LoginError("舊版伺服器清單中沒有這個分流")
        endpoint = LINE_SNAPSHOT[line_id][1:]
        with self._lock:
            if self._attempted or self._stopped.is_set():
                raise LoginError("此登入試驗已使用或取消；請重新開始")
            self._attempted = True
        formal = None
        try:
            verify = self._dial(endpoint)
            with self._lock:
                if self._stopped.is_set():
                    verify.close()
                    raise LoginError("登入已取消；不送出任何封包")
                self._socket = verify
            try:
                if self._stopped.is_set():
                    raise LoginError("登入已取消")
                verify.sendall(build_legacy_request(account, password, kind=0))
                self._reply_phase(
                    verify, kind=0, deadline=self._clock() + self._timeout)
            finally:
                with self._lock:
                    if self._socket is verify:
                        self._socket = None
                verify.close()

            if self._stopped.is_set():
                raise LoginError("登入已取消")
            formal = self._dial(endpoint)
            with self._lock:
                if self._stopped.is_set():
                    formal.close()
                    raise LoginError("登入已取消；不發送正式登入封包")
                self._socket = formal
            if self._stopped.is_set():
                raise LoginError("登入已取消；不發送正式登入封包")
            formal_decoder = decoder_for_legacy_fixture()
            formal.sendall(build_legacy_request(account, password, kind=2))
            slots = self._reply_phase(
                formal, kind=2, deadline=self._clock() + self._timeout,
                need_roles=True, decoder=formal_decoder)
            if not slots or self._stopped.is_set():
                raise LoginError("無法驗證舊版角色清單，拒絕選角")
            with self._lock:
                if self._socket is not formal or self._stopped.is_set():
                    raise LoginError("登入已被中斷")
                self._verified_slots = slots
                self._endpoint = endpoint
                self._formal_decoder = formal_decoder
            return LegacyTrialResult(True, True, slots)
        except (OSError, WireDecodeError) as error:
            self.close()
            raise LoginError("舊版登入通訊失敗，尚未驗證現行伺服器協定") from None
        except LoginError:
            self.close()
            raise

    def select_role(self, slot: int) -> LegacyRoleTrialResult:
        """Explicit legacy C63-2 and *both* mandatory S3-1/S1-11 responses.

        S1-11 alone is NOT a world-player snapshot. Strictly reject an
        incomplete or malformed S3-1, even if the "ready" event arrives.
        Legacy C12-1/C3-2 are emitted after complete initialization, then
        the socket closes. A persistent session requires a separately
        reviewed adapter and state publisher.
        """
        if type(slot) is not int or slot not in (1, 2):
            raise LoginError("角色槽位僅允許 1 或 2")
        with self._lock:
            connection = self._socket
            decoder = self._formal_decoder
            if (self._stopped.is_set() or connection is None or decoder is None
                    or slot not in self._verified_slots):
                raise LoginError("尚未收到有效的舊版角色清單")
        try:
            connection.sendall(_small_frame(63, 2, bytes((slot,))))
            player = None
            complete = False
            for packet in self._wait_packets(
                    connection, decoder, self._clock() + self._timeout,
                    phase="選角"):
                if (packet.main, packet.sub) == (3, 1):
                    try:
                        candidate = parse_legacy_world_player(packet)
                    except WireDecodeError:
                        raise LoginError("S3-1 角色資料格式與舊版不符，拒絕同步") from None
                    if player is not None and candidate.role_id != player.role_id:
                        raise LoginError("選角時收到不一致的角色資料")
                    player = candidate
                elif (packet.main, packet.sub) == (1, 11):
                    if packet.payload:
                        raise LoginError("舊版 S1-11 初始化訊號格式不符，停止試驗")
                    complete = True
                if player is not None and complete:
                    # Legacy SessionLogic sends these two acknowledgements only
                    # after both validated world data and initialization marker.
                    # This is still a one-shot experiment, never a trusted session.
                    for ack in build_legacy_world_init_acks():
                        if self._stopped.is_set():
                            raise LoginError("已中斷選角試驗，不送出初始化回覆")
                        connection.sendall(ack)
                    return LegacyRoleTrialResult(
                        slot, True, False, True, player.role_id,
                        player.character_name, player.scene, player.x, player.y,
                        init_acks_sent=True)
            raise LoginError("缺少完整的 S3-1 角色資料或 S1-11 初始化確認")
        except OSError:
            raise LoginError("選角期間連線中斷") from None
        finally:
            # Read-only compatibility observation, not a verified gameplay
            # session: no commands or automatic reconnect.
            self.close()
