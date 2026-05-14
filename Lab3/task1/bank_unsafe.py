"""
Задача 1: Банківські перекази БЕЗ синхронізації.
Демонструє Race Condition та Deadlock.
"""
import threading
import random
import time
import sys

N_ACCOUNTS = 120
N_THREADS = 1100
TRANSFER_DURATION = 1.5
INITIAL_MIN = 100
INITIAL_MAX = 1000

accounts = [random.randint(INITIAL_MIN, INITIAL_MAX) for _ in range(N_ACCOUNTS)]
locks = [threading.Lock() for _ in range(N_ACCOUNTS)]

transfers_done = 0
transfers_lock = threading.Lock()
stop_flag = threading.Event()
DEMO_DEADLOCK = "--deadlock" in sys.argv


def transfer_unsafe(src: int, dst: int, amount: int) -> None:
    """Read-modify-write без синхронізації.
    Race condition в CPython маскується GIL для коротких операцій, тому
    моделюємо реалістичну ситуацію: між read і write відбувається трохи
    "роботи" (валідація, логування, обчислення комісії). Микропауза дає
    шанс GIL переключити контекст саме між read і write — і race виникає
    закономірно при будь-якій кількості потоків > 1."""
    if accounts[src] >= amount:
        a = accounts[src]
        b = accounts[dst]
        # явний switch GIL — моделює реальну "роботу" між read і write
        time.sleep(0.00001)
        accounts[src] = a - amount
        accounts[dst] = b + amount


def transfer_with_deadlock(src: int, dst: int, amount: int) -> bool:
    """Захоплення локів у "природному" порядку src→dst — поганий патерн.
    transfer(A,B) і одночасно transfer(B,A) → циклічне очікування → deadlock."""
    if not locks[src].acquire(timeout=0.3):
        return False
    try:
        time.sleep(0.001)
        if not locks[dst].acquire(timeout=0.3):
            return False
        try:
            if accounts[src] >= amount:
                accounts[src] -= amount
                accounts[dst] += amount
                return True
            return False
        finally:
            locks[dst].release()
    finally:
        locks[src].release()


def worker():
    global transfers_done
    local_count = 0
    while not stop_flag.is_set():
        src = random.randrange(N_ACCOUNTS)
        dst = random.randrange(N_ACCOUNTS)
        if src == dst:
            continue
        amount = random.randint(1, 50)
        if DEMO_DEADLOCK:
            transfer_with_deadlock(src, dst, amount)
        else:
            transfer_unsafe(src, dst, amount)
        local_count += 1
    with transfers_lock:
        transfers_done += local_count


def main():
    initial_total = sum(accounts)
    print(f"[unsafe] Режим: {'DEADLOCK demo' if DEMO_DEADLOCK else 'RACE CONDITION demo'}")
    print(f"[unsafe] Рахунків: {N_ACCOUNTS}, потоків: {N_THREADS}")
    print(f"[unsafe] Сума ДО переказів: {initial_total}")

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(N_THREADS)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    time.sleep(TRANSFER_DURATION)
    stop_flag.set()

    deadline = time.perf_counter() + 1.0
    for t in threads:
        remaining = max(0.001, deadline - time.perf_counter())
        t.join(timeout=remaining)
    alive_after_join = sum(1 for t in threads if t.is_alive())
    elapsed = time.perf_counter() - t0

    final_total = sum(accounts)
    print(f"[unsafe] Сума ПІСЛЯ переказів: {final_total}")
    print(f"[unsafe] Δ (має бути 0): {final_total - initial_total}")
    print(f"[unsafe] Транзакцій: {transfers_done}")
    print(f"[unsafe] Активних потоків після зупинки (deadlock?): {alive_after_join}/{N_THREADS}")
    print(f"[unsafe] Часу: {elapsed:.3f} с")
    return {
        "initial_total": initial_total,
        "final_total": final_total,
        "delta": final_total - initial_total,
        "transfers": transfers_done,
        "deadlocked_threads": alive_after_join,
        "elapsed": elapsed,
    }


if __name__ == "__main__":
    main()
