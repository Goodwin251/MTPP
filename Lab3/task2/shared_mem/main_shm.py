"""
Задача 2, Метод 3 — Shared Memory.
Python main <-> C++ worker (worker_shm.exe / worker_shm).

Windows: використовуємо mmap.mmap на тимчасовий файл +
         C++ читає той самий файл через CreateFileMapping.
Linux:   multiprocessing.shared_memory (POSIX shm).

Запуск:
    python main_shm.py --n 50000
"""
import mmap, os, platform, struct, subprocess, sys, tempfile, time, argparse

HERE   = os.path.dirname(os.path.abspath(__file__))
EXE    = "worker_shm.exe" if platform.system() == "Windows" else "worker_shm"
WORKER = os.path.join(HERE, EXE)
SHM_NAME = "lab3_shm"
SHM_SIZE = 16

# offset layout
SEQ_OFF = 0;  ACK_OFF = 4;  VAL_IN = 8;  VAL_OUT = 12


def create_shm_windows(name: str, size: int):
    """На Windows: CreateFileMapping через mmap.mmap(tagname=name)."""
    mm = mmap.mmap(-1, size, tagname=name,
                   access=mmap.ACCESS_WRITE)
    mm.write(b'\x00' * size)
    mm.seek(0)
    return mm, None          # (mmap, path_для_cleanup)


def create_shm_linux(name: str, size: int):
    """На Linux: файл у /dev/shm або /tmp."""
    path = f"/dev/shm/{name}" if os.path.exists("/dev/shm") else f"/tmp/{name}"
    with open(path, "w+b") as f:
        f.write(b'\x00' * size)
    fh = open(path, "r+b")
    mm = mmap.mmap(fh.fileno(), size)
    fh.close()
    return mm, path


def r32(mm, off):
    mm.seek(off); return struct.unpack("<i", mm.read(4))[0]

def w32(mm, off, val):
    mm.seek(off); mm.write(struct.pack("<i", val))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    args = ap.parse_args()

    if not os.path.exists(WORKER):
        sys.exit(f"Не знайдено {WORKER}\n"
                 f"Скомпілюйте: g++ -O2 -std=c++17 worker_shm.cpp -o {EXE}")

    # Створюємо shared memory
    if platform.system() == "Windows":
        mm, shm_path = create_shm_windows(SHM_NAME, SHM_SIZE)
    else:
        mm, shm_path = create_shm_linux(SHM_NAME, SHM_SIZE)

    # Запускаємо C++ worker (він відкриє ту саму пам'ять за назвою)
    proc = subprocess.Popen(
        [WORKER, SHM_NAME],
        stderr=subprocess.PIPE,
    )
    time.sleep(0.3)   # чекаємо поки worker підключиться

    if proc.poll() is not None:
        err = proc.stderr.read().decode(errors="replace")
        sys.exit(f"Worker не запустився:\n{err}")

    print(f"[main-shm] C++ worker PID={proc.pid}, n={args.n}")

    lats = []
    t0 = time.perf_counter()

    for i in range(args.n):
        val = (i * 31 + 7) % 100_000
        new_seq = i + 1
        ts = time.perf_counter_ns()

        w32(mm, VAL_IN, val)
        w32(mm, SEQ_OFF, new_seq)    # сигнал для worker

        # Spin-wait: чекаємо ack від worker
        # Sleep(0) / time.sleep(0) — yield scheduler, без нього на 1 CPU зависає
        while r32(mm, ACK_OFF) != new_seq:
            time.sleep(0.00005)

        back = r32(mm, VAL_OUT)
        lats.append(time.perf_counter_ns() - ts)

        if back != val * 2:
            print(f"MISMATCH i={i}: sent={val}, got={back}", file=sys.stderr)

    total = time.perf_counter() - t0

    # Сигнал завершення
    w32(mm, SEQ_OFF, -1)
    proc.wait(timeout=3)
    mm.close()
    if shm_path:
        try: os.remove(shm_path)
        except OSError: pass

    lats.sort()
    r = {
        "method": "shared_memory (Python→C++)",
        "n": args.n,
        "total_ms":   round(total * 1000, 2),
        "throughput": round(args.n / total, 0),
        "mean_us":    round(sum(lats) / len(lats) / 1000, 2),
        "p50_us":     round(lats[len(lats) // 2] / 1000, 2),
        "p99_us":     round(lats[int(len(lats) * .99)] / 1000, 2),
    }
    print(f"[main-shm] Час: {r['total_ms']} мс | "
          f"Throughput: {r['throughput']:.0f}/с | "
          f"Latency mean={r['mean_us']} мкс  p99={r['p99_us']} мкс")
    return r


if __name__ == "__main__":
    main()
