"""
problems.py — демонстрація Race Condition і Deadlock.

Race Condition:
  Кілька потоків одночасно читають/пишуть grid[row][col] без захисту.
  Результат: частинки «зникають» або «множаться» — порушується інваріант.

Deadlock:
  Два потоки захоплюють локи в різному порядку:
    Потік A: lock(cell_1) → lock(cell_2)
    Потік B: lock(cell_2) → lock(cell_1)
  При зустрічному переміщенні виникає циклічне очікування.
  Детектується через acquire(timeout=...) — якщо потік зависає, це deadlock.
"""
import threading
import random
import time
from typing import List, Tuple
import config


# ─────────────────────────── RACE CONDITION ──────────────────────────────────

class UnsafeGrid:
    """Сітка БЕЗ синхронізації."""
    def __init__(self, size: int):
        self.size = size
        self.grid = [[0] * size for _ in range(size)]

    def move_unsafe(self, src_r: int, src_c: int,
                    dst_r: int, dst_c: int) -> None:
        """Read-modify-write без захисту → race condition."""
        if self.grid[src_r][src_c] > 0:
            # time.sleep(0) між read і write — дає GIL шанс переключитись
            # і гарантує відтворюваність race у Python
            val = self.grid[src_r][src_c]
            time.sleep(0)
            self.grid[src_r][src_c] = val - 1
            val2 = self.grid[dst_r][dst_c]
            time.sleep(0)
            self.grid[dst_r][dst_c] = val2 + 1

    def count(self) -> int:
        return sum(self.grid[r][c]
                   for r in range(self.size)
                   for c in range(self.size))


def demonstrate_race_condition(n_particles: int = 50,
                               n_steps: int = 100,
                               grid_size: int = 10) -> dict:
    """
    Запускає симуляцію без синхронізації.
    Повертає кількість частинок до і після — якщо різні, race є.
    """
    grid = UnsafeGrid(grid_size)
    rng = random.Random(config.MASTER_SEED)

    # Початкове розміщення
    positions = []
    for _ in range(n_particles):
        r, c = rng.randrange(grid_size), rng.randrange(grid_size)
        grid.grid[r][c] += 1
        positions.append([r, c])

    start_count = grid.count()
    deltas = []  # різниця після кожного прогону

    def worker(pid: int):
        local_rng = random.Random(pid)  # у unsafe версії — спільні дані, різні RNG
        pos = positions[pid]
        for _ in range(n_steps):
            dr = local_rng.choice([-1, 0, 1, 0])
            dc = local_rng.choice([0, -1, 0, 1])
            nr = max(0, min(grid_size - 1, pos[0] + dr))
            nc = max(0, min(grid_size - 1, pos[1] + dc))
            grid.move_unsafe(pos[0], pos[1], nr, nc)
            pos[0], pos[1] = nr, nc

    threads = [threading.Thread(target=worker, args=(i,))
               for i in range(n_particles)]
    t0 = time.perf_counter()
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.perf_counter() - t0

    end_count = grid.count()
    delta = end_count - start_count

    return {
        "mode": "race_condition_demo",
        "start_count": start_count,
        "end_count": end_count,
        "delta": delta,
        "race_detected": delta != 0,
        "elapsed_s": round(elapsed, 3),
    }


# ─────────────────────────── DEADLOCK ────────────────────────────────────────

_DEADLOCK_TIMEOUT = 0.5   # секунд — якщо acquire не вдається, це deadlock


def demonstrate_deadlock() -> dict:
    """
    Демонструє deadlock між двома потоками.
    Потік A: lock(cell_0,0) → sleep → lock(cell_0,1)
    Потік B: lock(cell_0,1) → sleep → lock(cell_0,0)
    Вони заблокуються один одного. Ми детектуємо це через acquire(timeout).
    """
    lock_00 = threading.Lock()
    lock_01 = threading.Lock()
    results = {"thread_a": None, "thread_b": None}

    def thread_a():
        lock_00.acquire()
        time.sleep(0.05)   # пауза — дає потоку B захопити lock_01
        # Тепер намагаємось захопити lock_01, але B вже тримає його
        got = lock_01.acquire(timeout=_DEADLOCK_TIMEOUT)
        if got:
            results["thread_a"] = "completed (no deadlock)"
            lock_01.release()
        else:
            results["thread_a"] = "DEADLOCKED (timeout on lock_01)"
        lock_00.release()

    def thread_b():
        lock_01.acquire()
        time.sleep(0.05)
        # Намагаємось захопити lock_00, але A вже тримає його
        got = lock_00.acquire(timeout=_DEADLOCK_TIMEOUT)
        if got:
            results["thread_b"] = "completed (no deadlock)"
            lock_00.release()
        else:
            results["thread_b"] = "DEADLOCKED (timeout on lock_00)"
        lock_01.release()

    ta = threading.Thread(target=thread_a)
    tb = threading.Thread(target=thread_b)
    t0 = time.perf_counter()
    ta.start(); tb.start()
    ta.join(); tb.join()
    elapsed = time.perf_counter() - t0

    deadlock_detected = ("DEADLOCKED" in str(results["thread_a"]) or
                         "DEADLOCKED" in str(results["thread_b"]))
    return {
        "mode": "deadlock_demo",
        "thread_a_result": results["thread_a"],
        "thread_b_result": results["thread_b"],
        "deadlock_detected": deadlock_detected,
        "elapsed_s": round(elapsed, 3),
    }


def demonstrate_deadlock_solution() -> dict:
    """
    Те саме, але з lock ordering: обидва потоки захоплюють локи
    у порядку зростання адреси (id(lock)) — deadlock неможливий.
    """
    lock_00 = threading.Lock()
    lock_01 = threading.Lock()
    results = {"thread_a": None, "thread_b": None}

    def acquire_ordered(l1, l2):
        """Завжди захоплюємо лок з меншим id першим."""
        first, second = (l1, l2) if id(l1) < id(l2) else (l2, l1)
        first.acquire()
        time.sleep(0.05)
        got = second.acquire(timeout=_DEADLOCK_TIMEOUT)
        return got, first, second

    def thread_a():
        got, first, second = acquire_ordered(lock_00, lock_01)
        results["thread_a"] = "completed" if got else "timeout (unexpected)"
        if got: second.release()
        first.release()

    def thread_b():
        got, first, second = acquire_ordered(lock_01, lock_00)
        results["thread_b"] = "completed" if got else "timeout (unexpected)"
        if got: second.release()
        first.release()

    ta = threading.Thread(target=thread_a)
    tb = threading.Thread(target=thread_b)
    t0 = time.perf_counter()
    ta.start(); tb.start()
    ta.join(); tb.join()
    elapsed = time.perf_counter() - t0

    return {
        "mode": "deadlock_solution",
        "thread_a_result": results["thread_a"],
        "thread_b_result": results["thread_b"],
        "deadlock_detected": False,
        "elapsed_s": round(elapsed, 3),
    }
