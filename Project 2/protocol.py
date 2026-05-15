"""
protocol.py — спільний протокол для сервера і клієнта.

Формат кожного повідомлення (по мережі):
  [4 байти: довжина JSON] + [JSON-рядок у UTF-8]

Типи повідомлень (поле "type"):
  Клієнт → Сервер:
    register      {username}
    text          {text}                     — broadcast
    private       {to, text}                 — приватне
    group_join    {group}
    group_leave   {group}
    group_msg     {group, text}
    file_send     {to, filename, size, data} — data: base64
    users         —                          — запит списку
    ping          —                          — keepalive

  Сервер → Клієнт:
    welcome       {username, server_ip, your_ip, online_users}
    broadcast     {from, from_ip, text, ts}
    private       {from, from_ip, text, ts}
    group_msg     {from, from_ip, group, text, ts}
    file          {from, from_ip, filename, size, data}
    users         {users: [{name, ip}]}
    event         {text, ts}                 — підключення/відключення
    offline_queue {messages: [...]}          — офлайн-черга при підключенні
    error         {text}
    pong          —
"""
import json
import struct
import socket
import base64
import time


HEADER = "!I"       # 4 байти, big-endian unsigned int
HEADER_SIZE = struct.calcsize(HEADER)
MAX_MSG = 64 * 1024 * 1024   # 64 МБ — максимальний розмір повідомлення


def send_msg(sock: socket.socket, msg: dict) -> None:
    """Серіалізує dict у JSON і надсилає з 4-байтовим заголовком довжини."""
    raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    header = struct.pack(HEADER, len(raw))
    sock.sendall(header + raw)


def recv_msg(sock: socket.socket) -> dict | None:
    """
    Читає одне повідомлення з сокета.
    Повертає dict або None якщо з'єднання закрите.
    """
    raw_hdr = _recv_exact(sock, HEADER_SIZE)
    if raw_hdr is None:
        return None
    length = struct.unpack(HEADER, raw_hdr)[0]
    if length > MAX_MSG:
        raise ValueError(f"Повідомлення завелике: {length} байт")
    raw_body = _recv_exact(sock, length)
    if raw_body is None:
        return None
    return json.loads(raw_body.decode("utf-8"))


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Читає рівно n байт. Повертає None при EOF."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def ts() -> str:
    """Поточна мітка часу у форматі HH:MM:SS."""
    return time.strftime("%H:%M:%S")


def file_to_b64(path: str) -> tuple[str, int]:
    """Читає файл і кодує в base64. Повертає (b64_string, size_bytes)."""
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("ascii"), len(data)


def b64_to_file(b64_str: str, path: str) -> int:
    """Декодує base64 і зберігає у файл. Повертає розмір."""
    data = base64.b64decode(b64_str)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)
