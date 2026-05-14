"""
Задача 2, Метод 1 — Pipe.
Python main <-> C++ worker (worker_pipe.exe / worker_pipe).

Запуск:
    python main_pipe.py --n 50000
"""
import os, platform, struct, subprocess, sys, time, argparse, json

HERE = os.path.dirname(os.path.abspath(__file__))
EXE  = "worker_pipe.exe" if platform.system() == "Windows" else "worker_pipe"
WORKER = os.path.join(HERE, EXE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    args = ap.parse_args()

    if not os.path.exists(WORKER):
        sys.exit(f"Не знайдено {WORKER}\n"
                 f"Скомпілюйте: g++ -O2 -std=c++17 worker_pipe.cpp -o {EXE}")

    proc = subprocess.Popen(
        [WORKER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,   # stderr C++ не блокує — воркер пише мало
        bufsize=0,
    )

    print(f"[main-pipe] n={args.n}, worker PID={proc.pid}")
    lats = []
    t0 = time.perf_counter()

    for i in range(args.n):
        val = (i * 31 + 7) % 100_000
        ts = time.perf_counter_ns()

        proc.stdin.write(struct.pack("<i", val))

        buf = b""
        while len(buf) < 4:
            chunk = proc.stdout.read(4 - len(buf))
            if not chunk:
                proc.kill()
                sys.exit(f"EOF від воркера на i={i}")
            buf += chunk

        back = struct.unpack("<i", buf)[0]
        lats.append(time.perf_counter_ns() - ts)

        if back != val * 2:
            print(f"MISMATCH i={i}: sent={val}, got={back}", file=sys.stderr)

    total = time.perf_counter() - t0
    proc.stdin.close()
    proc.wait(timeout=3)

    lats.sort()
    r = {
        "method": "pipe (Python→C++)",
        "n": args.n,
        "total_ms":   round(total * 1000, 2),
        "throughput": round(args.n / total, 0),
        "mean_us":    round(sum(lats) / len(lats) / 1000, 2),
        "p50_us":     round(lats[len(lats) // 2] / 1000, 2),
        "p99_us":     round(lats[int(len(lats) * .99)] / 1000, 2),
    }
    print(f"[main-pipe] Час: {r['total_ms']} мс | "
          f"Throughput: {r['throughput']:.0f}/с | "
          f"Latency mean={r['mean_us']} мкс  p99={r['p99_us']} мкс")
    return r


if __name__ == "__main__":
    main()
