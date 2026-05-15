"""
client.py — консольний клієнт чату.

Запуск:
    python client.py --host <IP_СЕРВЕРА> --port 9000 --name Alice

Команди:
  /users                    — список учасників (ім'я + IPv4)
  /msg <user> <текст>       — приватне повідомлення
  /join <group>             — приєднатись до групи
  /leave <group>            — вийти з групи
  /g <group> <текст>        — повідомлення у групу
  /file <user> <шлях>       — надіслати файл
  /save <шлях>              — зберегти останній отриманий файл
  /help                     — довідка
  /quit                     — вихід
"""
import argparse
import os
import sys
import threading
import time

import protocol as P


# ── Стан клієнта ─────────────────────────────────────────────────────────────
class ClientState:
    def __init__(self):
        self.username  = ""
        self.server_ip = ""
        self.my_ip     = ""
        self.sock      = None
        self._last_file = None
        self._lock = threading.Lock()

    def set_last_file(self, msg):
        with self._lock:
            self._last_file = msg

    def get_last_file(self):
        with self._lock:
            return self._last_file

    def prompt(self):
        return f"[{self.my_ip}] {self.username} > "


state = ClientState()

# Єдиний лок для будь-якого виводу в stdout
_print_lock = threading.Lock()


def println(text: str):
    """
    Виводить рядок і відновлює рядок введення.
    Єдина функція що пише в stdout після старту receiver_thread.
    """
    with _print_lock:
        sys.stdout.write(f"\r{' ' * 80}\r")   # затираємо prompt
        sys.stdout.write(text + "\n")
        sys.stdout.write(state.prompt())
        sys.stdout.flush()


# ── Форматування ──────────────────────────────────────────────────────────────
def fmt_broadcast(msg):
    return f"[{msg['ts']}] [{msg['from_ip']}] {msg['from']}: {msg['text']}"

def fmt_private(msg):
    return (f"[{msg['ts']}] [ПРИВАТНО від {msg['from_ip']}] "
            f"{msg['from']}: {msg['text']}")

def fmt_group(msg):
    return (f"[{msg['ts']}] [{msg['group']}] "
            f"[{msg['from_ip']}] {msg['from']}: {msg['text']}")

def fmt_file(msg):
    kb = msg['size'] / 1024
    return (f"[{msg['ts']}] [ФАЙЛ від {msg['from_ip']}] "
            f"{msg['from']} надіслав {msg['filename']} ({kb:.1f} КБ)"
            f"  ← /save <шлях> щоб зберегти")

def fmt_event(msg):
    return f"[{msg['ts']}] {msg['text']}"

def fmt_users(users):
    lines = ["─── Учасники онлайн ───"]
    for u in users:
        lines.append(f"  {u['name']:20s}  {u['ip']}")
    lines.append("───────────────────────")
    return "\n".join(lines)


# ── Потік отримання повідомлень ───────────────────────────────────────────────
def receiver_thread():
    while True:
        try:
            msg = P.recv_msg(state.sock)
        except Exception:
            msg = None
        if msg is None:
            println("!!! З'єднання з сервером розірване")
            os._exit(0)

        mtype = msg.get("type", "")

        if mtype == "broadcast":
            println(fmt_broadcast(msg))
        elif mtype == "private":
            println(fmt_private(msg))
        elif mtype == "group_msg":
            println(fmt_group(msg))
        elif mtype == "file":
            state.set_last_file(msg)
            println(fmt_file(msg))
        elif mtype == "event":
            println(fmt_event(msg))
        elif mtype == "users":
            for line in fmt_users(msg["users"]).split("\n"):
                println(line)
        elif mtype == "error":
            println(f"[ПОМИЛКА] {msg['text']}")
        elif mtype == "offline_queue":
            queue = msg.get("messages", [])
            if queue:
                println(f"─── {len(queue)} офлайн-повідомлень ───")
                for m in queue:
                    mt = m.get("type", "")
                    if mt == "private":
                        println(fmt_private(m))
                    elif mt == "file":
                        state.set_last_file(m)
                        println(fmt_file(m))
        elif mtype == "pong":
            pass


# ── Keepalive ─────────────────────────────────────────────────────────────────
def ping_thread():
    while True:
        time.sleep(30)
        try:
            P.send_msg(state.sock, {"type": "ping"})
        except OSError:
            break


# ── Обробка команд ────────────────────────────────────────────────────────────
def handle_input(line: str):
    """
    Обробляє введений рядок.
    Кожна гілка ПОВИННА викликати println — щоб prompt відновився.
    Якщо виводити нічого, викликаємо println("") — порожній рядок.
    """
    line = line.strip()
    if not line:
        # порожній Enter — просто оновлюємо prompt без зайвого рядка
        with _print_lock:
            sys.stdout.write(state.prompt())
            sys.stdout.flush()
        return

    if line in ("/quit", "/exit", "/q"):
        print("\nДо побачення!")
        os._exit(0)

    elif line == "/help":
        println(
            "/users                  — список учасників (ім'я + IPv4)\n"
            "/msg <user> <текст>     — приватне повідомлення\n"
            "/join <group>           — приєднатись до групи\n"
            "/leave <group>          — вийти з групи\n"
            "/g <group> <текст>      — повідомлення у групу\n"
            "/file <user> <шлях>     — надіслати файл\n"
            "/save <шлях>            — зберегти останній отриманий файл\n"
            "/quit                   — вихід"
        )

    elif line == "/users":
        # відповідь прийде через receiver_thread → println
        P.send_msg(state.sock, {"type": "users"})

    elif line.startswith("/msg "):
        parts = line[5:].split(" ", 1)
        if len(parts) < 2:
            println("[!] Формат: /msg <user> <текст>")
            return
        to, text = parts
        P.send_msg(state.sock, {"type": "private", "to": to, "text": text})
        println(f"[{P.ts()}] [→ {to}]: {text}")

    elif line.startswith("/join "):
        group = line[6:].strip()
        P.send_msg(state.sock, {"type": "group_join", "group": group})
        # підтвердження прийде через event від сервера

    elif line.startswith("/leave "):
        group = line[7:].strip()
        P.send_msg(state.sock, {"type": "group_leave", "group": group})

    elif line.startswith("/g "):
        parts = line[3:].split(" ", 1)
        if len(parts) < 2:
            println("[!] Формат: /g <group> <текст>")
            return
        group, text = parts
        P.send_msg(state.sock, {"type": "group_msg", "group": group, "text": text})
        println(f"[{P.ts()}] [{group}] [{state.my_ip}] {state.username}: {text}")

    elif line.startswith("/file "):
        parts = line[6:].split(" ", 1)
        if len(parts) < 2:
            println("[!] Формат: /file <user> <шлях>")
            return
        to, path = parts[0], parts[1].strip()
        if not os.path.exists(path):
            println(f"[!] Файл не знайдено: {path}")
            return
        try:
            b64, size = P.file_to_b64(path)
            filename = os.path.basename(path)
            P.send_msg(state.sock, {
                "type": "file_send",
                "to": to,
                "filename": filename,
                "size": size,
                "data": b64,
            })
            println(f"[{P.ts()}] [ФАЙЛ → {to}]: {filename} ({size/1024:.1f} КБ) надіслано")
        except Exception as e:
            println(f"[!] Помилка відправки: {e}")

    elif line.startswith("/save "):
        path = line[6:].strip()
        file_msg = state.get_last_file()
        if not file_msg:
            println("[!] Немає файлу для збереження")
            return
        try:
            size = P.b64_to_file(file_msg["data"], path)
            println(f"[OK] Збережено: {path} ({size/1024:.1f} КБ)")
        except Exception as e:
            println(f"[!] Помилка збереження: {e}")

    elif line.startswith("/"):
        println("[!] Невідома команда. /help — довідка")

    else:
        # Broadcast — відображаємо у себе і надсилаємо
        P.send_msg(state.sock, {"type": "text", "text": line})
        println(f"[{P.ts()}] [{state.my_ip}] {state.username}: {line}")


# ── Підключення ───────────────────────────────────────────────────────────────
def connect(host, port, username):
    import socket as _socket
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.setsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY, 1)
    try:
        sock.connect((host, port))
    except ConnectionRefusedError:
        print(f"[!] Не вдалося підключитися до {host}:{port}")
        return False

    state.sock = sock
    P.send_msg(sock, {"type": "register", "username": username})
    resp = P.recv_msg(sock)

    if resp is None:
        print("[!] Сервер не відповів"); return False
    if resp.get("type") == "error":
        print(f"[!] {resp['text']}"); return False
    if resp.get("type") != "welcome":
        print(f"[!] Неочікувана відповідь: {resp}"); return False

    state.username  = resp["username"]
    state.server_ip = resp["server_ip"]
    state.my_ip     = resp["your_ip"]

    print(f"\n{'='*55}")
    print(f"  Сервер:    {resp['server_ip']}:{port}")
    print(f"  Логін:     {state.username}")
    print(f"  Ваша IPv4: {state.my_ip}")
    online = resp.get("online_users", [])
    if online:
        print(f"  Онлайн:    " +
              ", ".join(f"{u['name']}({u['ip']})" for u in online))
    print(f"{'='*55}")
    print("  Введіть повідомлення або /help для довідки")

    offline = resp.get("offline_queue", [])
    if offline:
        print(f"─── {len(offline)} офлайн-повідомлень ───")
        for m in offline:
            mt = m.get("type", "")
            if mt == "private":
                print(fmt_private(m))
            elif mt == "file":
                state.set_last_file(m)
                print(fmt_file(m))

    return True


# ── Головний цикл введення ────────────────────────────────────────────────────
def input_loop():
    """
    Читає рядки з stdin.
    НЕ друкує prompt сам — це робить println() після кожного виводу.
    Перший prompt друкується один раз перед першим readline().
    """
    with _print_lock:
        sys.stdout.write(state.prompt())
        sys.stdout.flush()

    while True:
        try:
            line = sys.stdin.readline()
            if not line:        # EOF
                break
        except KeyboardInterrupt:
            break

        handle_input(line)
        # Якщо handle_input не викликав println (наприклад /users, /join),
        # prompt все одно треба відновити — receiver_thread зробить це
        # при надходженні відповіді від сервера. Для команд без відповіді
        # (такого у нас немає) — нічого страшного, prompt з'явиться при
        # наступному вхідному повідомленні.

    print("\nВихід.")
    os._exit(0)


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Чат-клієнт")
    ap.add_argument("--host", required=True, help="IP сервера")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--name", default="", help="Нікнейм")
    args = ap.parse_args()

    username = args.name.strip()
    while not username:
        username = input("Ваш нікнейм: ").strip()

    print(f"Підключення до {args.host}:{args.port}...")
    if not connect(args.host, args.port, username):
        sys.exit(1)

    threading.Thread(target=receiver_thread, daemon=True).start()
    threading.Thread(target=ping_thread,     daemon=True).start()
    input_loop()


if __name__ == "__main__":
    main()
