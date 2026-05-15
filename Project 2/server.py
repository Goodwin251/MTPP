"""
server.py — багатопотоковий чат-сервер.

Запуск:
    python server.py [--host 0.0.0.0] [--port 9000]

Архітектура паралелізму:
  - Головний потік: accept() — чекає нових підключень.
  - Кожне підключення → окремий потік (ClientHandler).
  - Спільні структури (clients, groups, offline) захищені threading.Lock.
  - Broadcast і private відправляються з потоку відправника через лок.
  - Журнал подій → chat.log (захищений FileHandler з logging).
"""
import argparse
import logging
import os
import socket
import threading
import time
from typing import Optional

import protocol as P

# ── Логування ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("chat.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("server")


# ── Спільний стан сервера ─────────────────────────────────────────────────────
class ServerState:
    def __init__(self):
        self._lock = threading.Lock()
        # {username: ClientHandler}
        self.clients: dict[str, "ClientHandler"] = {}
        # {group_name: set(username)}
        self.groups: dict[str, set[str]] = {}
        # {username: [msg_dict, ...]}  — офлайн-черга
        self.offline: dict[str, list[dict]] = {}

    # ── клієнти ───────────────────────────────────────────────────────────────
    def add_client(self, handler: "ClientHandler") -> bool:
        """Повертає False якщо ім'я зайнято."""
        with self._lock:
            if handler.username in self.clients:
                return False
            self.clients[handler.username] = handler
            return True

    def remove_client(self, username: str):
        with self._lock:
            self.clients.pop(username, None)
            for members in self.groups.values():
                members.discard(username)

    def get_client(self, username: str) -> Optional["ClientHandler"]:
        with self._lock:
            return self.clients.get(username)

    def online_users(self) -> list[dict]:
        with self._lock:
            return [{"name": u, "ip": h.client_ip}
                    for u, h in self.clients.items()]

    # ── групи ─────────────────────────────────────────────────────────────────
    def join_group(self, username: str, group: str):
        with self._lock:
            self.groups.setdefault(group, set()).add(username)

    def leave_group(self, username: str, group: str):
        with self._lock:
            if group in self.groups:
                self.groups[group].discard(username)

    def group_members(self, group: str) -> list[str]:
        with self._lock:
            return list(self.groups.get(group, set()))

    # ── офлайн-черга ──────────────────────────────────────────────────────────
    def enqueue_offline(self, username: str, msg: dict):
        with self._lock:
            self.offline.setdefault(username, []).append(msg)

    def pop_offline(self, username: str) -> list[dict]:
        with self._lock:
            msgs = self.offline.pop(username, [])
            return msgs

    # ── broadcast ─────────────────────────────────────────────────────────────
    def broadcast(self, msg: dict, exclude: str = None):
        """Надсилає повідомлення всім (крім exclude)."""
        with self._lock:
            targets = [(u, h) for u, h in self.clients.items() if u != exclude]
        for _, h in targets:
            h.send(msg)


state = ServerState()


# ── Обробник одного клієнта ───────────────────────────────────────────────────
class ClientHandler(threading.Thread):
    def __init__(self, sock: socket.socket, addr: tuple, server_ip: str):
        super().__init__(daemon=True)
        self.sock = sock
        self.addr = addr
        self.client_ip: str = addr[0]
        self.server_ip: str = server_ip
        self.username: str = ""
        self._registered = False             # True тільки після успішного add_client
        self._send_lock = threading.Lock()   # серіалізує send() для цього клієнта

    def send(self, msg: dict):
        """Потокобезпечне надсилання одного повідомлення."""
        with self._send_lock:
            try:
                P.send_msg(self.sock, msg)
            except OSError:
                pass

    def run(self):
        try:
            self._handshake()
            self._loop()
        except Exception as e:
            log.warning(f"[{self.addr}] помилка: {e}")
        finally:
            self._disconnect()

    # ── реєстрація ────────────────────────────────────────────────────────────
    def _handshake(self):
        msg = P.recv_msg(self.sock)
        if msg is None or msg.get("type") != "register":
            raise ConnectionError("Очікувався register")
        username = msg.get("username", "").strip()
        if not username or len(username) > 32:
            self.send({"type": "error", "text": "Невірне ім'я"})
            raise ConnectionError("Невірне ім'я")

        self.username = username
        if not state.add_client(self):
            self.send({"type": "error",
                       "text": f"Ім'я '{username}' вже зайняте"})
            raise ConnectionError("Ім'я зайняте")

        self._registered = True   # ← тільки тут клієнт вважається активним

        # Доставляємо офлайн-чергу
        offline = state.pop_offline(username)

        self.send({
            "type": "welcome",
            "username": username,
            "server_ip": self.server_ip,
            "your_ip": self.client_ip,
            "online_users": state.online_users(),
            "offline_queue": offline,
        })

        # Сповіщаємо всіх про нового учасника
        event_msg = {
            "type": "event",
            "text": f">>> {username} ({self.client_ip}) приєднався до чату",
            "ts": P.ts(),
        }
        state.broadcast(event_msg, exclude=username)
        log.info(f"CONNECT {username} @ {self.client_ip}")

    # ── основний цикл ─────────────────────────────────────────────────────────
    def _loop(self):
        while True:
            msg = P.recv_msg(self.sock)
            if msg is None:
                break
            mtype = msg.get("type", "")

            if mtype == "text":
                self._handle_broadcast(msg)
            elif mtype == "private":
                self._handle_private(msg)
            elif mtype == "group_join":
                self._handle_group_join(msg)
            elif mtype == "group_leave":
                self._handle_group_leave(msg)
            elif mtype == "group_msg":
                self._handle_group_msg(msg)
            elif mtype == "file_send":
                self._handle_file(msg)
            elif mtype == "users":
                self.send({"type": "users", "users": state.online_users()})
            elif mtype == "ping":
                self.send({"type": "pong"})

    # ── обробники типів ───────────────────────────────────────────────────────
    def _handle_broadcast(self, msg: dict):
        out = {
            "type": "broadcast",
            "from": self.username,
            "from_ip": self.client_ip,
            "text": msg["text"],
            "ts": P.ts(),
        }
        state.broadcast(out, exclude=self.username)
        log.info(f"BROADCAST {self.username}: {msg['text'][:80]}")

    def _handle_private(self, msg: dict):
        to = msg.get("to", "")
        text = msg.get("text", "")
        out = {
            "type": "private",
            "from": self.username,
            "from_ip": self.client_ip,
            "text": text,
            "ts": P.ts(),
        }
        target = state.get_client(to)
        if target:
            target.send(out)
            log.info(f"PRIVATE {self.username}→{to}: {text[:80]}")
        else:
            # Одержувач офлайн — зберігаємо
            state.enqueue_offline(to, out)
            self.send({"type": "event",
                       "text": f"[сервер] {to} офлайн, повідомлення збережено",
                       "ts": P.ts()})
            log.info(f"OFFLINE {self.username}→{to}: {text[:80]}")

    def _handle_group_join(self, msg: dict):
        group = msg.get("group", "").strip()
        if not group:
            return
        state.join_group(self.username, group)
        self.send({"type": "event",
                   "text": f"[сервер] Ви приєдналися до групи '{group}'",
                   "ts": P.ts()})
        # Сповіщаємо учасників групи
        note = {
            "type": "event",
            "text": f"[{group}] {self.username} приєднався до групи",
            "ts": P.ts(),
        }
        for uname in state.group_members(group):
            if uname != self.username:
                h = state.get_client(uname)
                if h:
                    h.send(note)
        log.info(f"GROUP_JOIN {self.username} → {group}")

    def _handle_group_leave(self, msg: dict):
        group = msg.get("group", "").strip()
        state.leave_group(self.username, group)
        self.send({"type": "event",
                   "text": f"[сервер] Ви вийшли з групи '{group}'",
                   "ts": P.ts()})
        log.info(f"GROUP_LEAVE {self.username} ← {group}")

    def _handle_group_msg(self, msg: dict):
        group = msg.get("group", "")
        text = msg.get("text", "")
        members = state.group_members(group)
        if self.username not in members:
            self.send({"type": "error",
                       "text": f"Ви не в групі '{group}'"})
            return
        out = {
            "type": "group_msg",
            "from": self.username,
            "from_ip": self.client_ip,
            "group": group,
            "text": text,
            "ts": P.ts(),
        }
        for uname in members:
            if uname != self.username:
                h = state.get_client(uname)
                if h:
                    h.send(out)
        log.info(f"GROUP {self.username}@{group}: {text[:80]}")

    def _handle_file(self, msg: dict):
        to = msg.get("to", "")
        out = {
            "type": "file",
            "from": self.username,
            "from_ip": self.client_ip,
            "filename": msg.get("filename", "file"),
            "size": msg.get("size", 0),
            "data": msg.get("data", ""),
            "ts": P.ts(),
        }
        target = state.get_client(to)
        if target:
            target.send(out)
            log.info(f"FILE {self.username}→{to}: {msg.get('filename')} "
                     f"({msg.get('size',0)} байт)")
        else:
            state.enqueue_offline(to, out)
            self.send({"type": "event",
                       "text": f"[сервер] {to} офлайн, файл збережено",
                       "ts": P.ts()})

    # ── відключення ───────────────────────────────────────────────────────────
    def _disconnect(self):
        if self._registered:
            state.remove_client(self.username)
            event_msg = {
                "type": "event",
                "text": f"<<< {self.username} ({self.client_ip}) покинув чат",
                "ts": P.ts(),
            }
            state.broadcast(event_msg)
            log.info(f"DISCONNECT {self.username} @ {self.client_ip}")
        try:
            self.sock.close()
        except OSError:
            pass


# ── Головний потік: accept ────────────────────────────────────────────────────
def get_local_ip() -> str:
    """Визначає локальну IPv4-адресу сервера."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main():
    ap = argparse.ArgumentParser(description="Чат-сервер")
    ap.add_argument("--host", default="0.0.0.0",
                    help="Адреса прослуховування (за замовч. 0.0.0.0)")
    ap.add_argument("--port", type=int, default=9000,
                    help="Порт (за замовч. 9000)")
    args = ap.parse_args()

    server_ip = get_local_ip()
    log.info(f"Сервер запускається на {server_ip}:{args.port}")
    log.info("Клієнти підключаються командою: python client.py "
             f"--host {server_ip} --port {args.port}")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(64)
    log.info(f"Очікую підключення на {args.host}:{args.port} ...")

    try:
        while True:
            conn, addr = srv.accept()
            # TCP_NODELAY — важливо для інтерактивного чату
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            handler = ClientHandler(conn, addr, server_ip)
            handler.start()
            log.info(f"Нове підключення від {addr[0]}:{addr[1]}, "
                     f"активних потоків: {threading.active_count()-1}")
    except KeyboardInterrupt:
        log.info("Сервер зупинено.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
