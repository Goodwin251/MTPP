"""
Задача 1: Банківські перекази З синхронізацією.
Рішення проблем:
  - Race Condition: per-account threading.Lock + захоплення обох локів перед read-modify-write.
  - Deadlock: lock ordering — завжди захоплюємо лок з меншим id першим (lock hierarchy).
"""
import threading
import random
import time

N_ACCOUNTS = 120
N_THREADS = 1100
TRANSFER_DURATION = 3.0
INITIAL_MIN = 100
INITIAL_MAX = 1000

accounts = [random.randint(INITIAL_MIN, INITIAL_MAX) for _ in range(N_ACCOUNTS)]
locks = [threading.Lock() for _ in range(N_ACCOUNTS)]

transfers_done = 0
transfers_failed = 0
stats_lock = threading.Lock()
stop_flag = threading.Event()


def transfer_safe(src: int, dst: int, amount: int) -> bool:
    """Безпечний переказ. Дві ключові ідеї:
      1) Беремо ОБИДВА локи перед будь-якою операцією з балансом.
      2) Захоплюємо в порядку зростання id, незалежно від напрямку переказу.
         Це гарантує відсутність циклічного очікування (Coffman conditions).
    """
    first, second = (src, dst) if src < dst else (dst, src)
    with locks[first]:
        with locks[second]:
            if accounts[src] >= amount:
                accounts[src] -= amount
                accounts[dst] += amount
                return True
            return False


def worker():
    global transfers_done, transfers_failed
    local_ok = 0
    local_fail = 0
    while not stop_flag.is_set():
        src = random.randrange(N_ACCOUNTS)
        dst = random.randrange(N_ACCOUNTS)
        if src == dst:
            continue
        amount = random.randint(1, 50)
        if transfer_safe(src, dst, amount):
            local_ok += 1
        else:
            local_fail += 1
    with stats_lock:
        transfers_done += local_ok
        transfers_failed += local_fail


def main():
    initial_total = sum(accounts)
    print(f"[safe] Рахунків: {N_ACCOUNTS}, потоків: {N_THREADS}")
    print(f"[safe] Сума ДО переказів: {initial_total}")

    threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    time.sleep(TRANSFER_DURATION)
    stop_flag.set()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t0

    final_total = sum(accounts)
    print(f"[safe] Сума ПІСЛЯ переказів: {final_total}")
    print(f"[safe] Дельта (має бути 0): {final_total - initial_total}")
    print(f"[safe] Успішних транзакцій: {transfers_done}")
    print(f"[safe] Відхилених (недостатньо коштів): {transfers_failed}")
    print(f"[safe] Часу: {elapsed:.3f} с")
    return {
        "initial_total": initial_total,
        "final_total": final_total,
        "delta": final_total - initial_total,
        "transfers": transfers_done,
        "failed": transfers_failed,
        "elapsed": elapsed,
    }


if __name__ == "__main__":
    main()
