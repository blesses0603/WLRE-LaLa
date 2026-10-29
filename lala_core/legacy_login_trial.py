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
    decoder_for_legacy_fixture, OLD_TX_XOR,
)
from .server_probe import LINE_SNAPSHOT
from .wire import WireDecodeError


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

    def close(self):
        self._stopped.set()
        with self._lock:
            connection, self._socket = self._socket, None
            self._verified_slots = ()
            self._endpoint = None
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

    def _wait_packets(self, connection, decoder, deadline):
        packets_seen = 0
        while not self._stopped.is_set() and self._clock() < deadline:
            try:
                data = connection.recv(8192)
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                raise LoginError("登入期間 TCP 連線中斷") from None
            if not data:
                raise LoginError("伺服器在完成舊版登入協定前關閉連線")
            try:
                packets = decoder.feed(data)
            except WireDecodeError:
                raise LoginError("收到不同於舊版的封包格式；停止登入試驗") from None
            for packet in packets:
                packets_seen += 1
                if packets_seen > 512:
                    raise LoginError("伺服器封包數量超出登入試驗上限")
                if (packet.main, packet.sub) == (1, 23):
                    try:
                        connection.sendall(_small_frame(63, 5))
                    except OSError:
                        raise LoginError("舊版心跳回覆送出失敗") from None
                    continue
                yield packet
        if self._stopped.is_set():
            raise LoginError("已中斷登入試驗")
        raise LoginError("舊版登入回覆逾時；未確認目前協定")

    def _reply_phase(self, connection, *, kind, deadline, need_roles=False):
        decoder = decoder_for_legacy_fixture()
        accepted, slots = False, ()
        for packet in self._wait_packets(connection, decoder, deadline):
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
            formal.sendall(build_legacy_request(account, password, kind=2))
            slots = self._reply_phase(
                formal, kind=2, deadline=self._clock() + self._timeout,
                need_roles=True)
            if not slots or self._stopped.is_set():
                raise LoginError("無法驗證舊版角色清單，拒絕選角")
            with self._lock:
                if self._socket is not formal or self._stopped.is_set():
                    raise LoginError("登入已被中斷")
                self._verified_slots = slots
                self._endpoint = endpoint
            return LegacyTrialResult(True, True, slots)
        except (OSError, WireDecodeError) as error:
            self.close()
            raise LoginError("舊版登入通訊失敗，尚未驗證現行伺服器協定") from None
        except LoginError:
            self.close()
            raise

    def select_role(self, slot: int) -> LegacyRoleTrialResult:
        if type(slot) is not int or slot not in (1, 2):
            raise LoginError("角色槽位僅允許 1 或 2")
        with self._lock:
            connection = self._socket
            if self._stopped.is_set() or connection is None or slot not in self._verified_slots:
                raise LoginError("尚未收到有效的舊版角色清單")
        try:
            connection.sendall(_small_frame(63, 2, bytes((slot,))))
            reader = decoder_for_legacy_fixture()
            for packet in self._wait_packets(
                    connection, reader, self._clock() + self._timeout):
                if (packet.main, packet.sub) == (3, 1):
                    # This is evidence of an old-format world-player packet,
                    # not a decoded/verified modern authoritative character.
                    if len(packet.payload) < 10:
                        raise LoginError("角色資料封包長度不足")
                    return LegacyRoleTrialResult(slot, True)
                if (packet.main, packet.sub) == (1, 11):
                    return LegacyRoleTrialResult(slot, True)
            raise LoginError("選角沒有收到舊版的世界資料訊號")
        except OSError:
            raise LoginError("選角期間連線中斷") from None
        finally:
            # This prototype cannot maintain an audited gameplay session.
            # Close explicitly; never claim the account remains online.
            self.close()
