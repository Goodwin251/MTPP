"""
Задача 2, Метод 2 — TCP Socket.
Python main (сервер) <-> C++ worker (клієнт, підключається до localhost).

Запуск:
    python main_socket.py --n 50000
"""
import os, platform, socket, struct, subprocess, sys, time, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
EXE  = "worker_socket.exe" if platform.system() == "Windows" else "worker_socket"
WORKER = os.path.join(HERE, EXE)
PORT = 9877


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    args = ap.parse_args()

    if not os.path.exists(WORKER):
        sys.exit(f"Не знайдено {WORKER}\n"
                 f"Скомпілюйте: g++ -O2 -std=c++17 worker_socket.cpp "
                 f"-o {EXE} -lws2_32")

    # Відкриваємо серверний сокет ДО запуску воркера
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(1)

    proc = subprocess.Popen(
        [WORKER, str(PORT)],
        stderr=subprocess.PIPE,
    )

    conn, addr = srv.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print(f"[main-socket] C++ worker підключився з {addr}, n={args.n}")

    lats = []
    t0 = time.perf_counter()

    for i in range(args.n):
        val = (i * 31 + 7) % 100_000
        ts = time.perf_counter_ns()

        conn.sendall(struct.pack("<i", val))

        buf = b""
        while len(buf) < 4:
            chunk = conn.recv(4 - len(buf))
            if not chunk:
                proc.kill()
                sys.exit(f"Socket EOF на i={i}")
            buf += chunk

        back = struct.unpack("<i", buf)[0]
        lats.append(time.perf_counter_ns() - ts)

        if back != val * 2:
            print(f"MISMATCH i={i}: sent={val}, got={back}", file=sys.stderr)

    total = time.perf_counter() - t0
    conn.close()
    srv.close()
    proc.wait(timeout=3)

    lats.sort()
    r = {
        "method": "socket (Python→C++)",
        "n": args.n,
        "total_ms":   round(total * 1000, 2),
        "throughput": round(args.n / total, 0),
        "mean_us":    round(sum(lats) / len(lats) / 1000, 2),
        "p50_us":     round(lats[len(lats) // 2] / 1000, 2),
        "p99_us":     round(lats[int(len(lats) * .99)] / 1000, 2),
    }
    print(f"[main-socket] Час: {r['total_ms']} мс | "
          f"Throughput: {r['throughput']:.0f}/с | "
          f"Latency mean={r['mean_us']} мкс  p99={r['p99_us']} мкс")
    return r


if __name__ == "__main__":
    main()
