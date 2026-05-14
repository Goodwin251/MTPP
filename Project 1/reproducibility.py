"""
reproducibility.py — демонстрація задачі A: seed + відтворюваність.

Ідея: запускаємо симуляцію двічі з однаковим MASTER_SEED.
Оскільки кожна частинка має власний RNG (seed = MASTER_SEED + particle_id),
траєкторії детерміновані і не залежать від порядку виконання потоків.
Фінальні позиції частинок у двох запусках мають бути ідентичні.

Це вирішує задачу A: "Задання seed та забезпечення відтворюваності симуляції".
"""
import random
import threading
import time
from typing import List, Tuple
import config


def run_reproducible(master_seed: int,
                     grid_size: int = 20,
                     n_particles: int = 50,
                     n_steps: int = 200) -> Tuple[List[List[int]], float]:
    """
    Один запуск симуляції. Повертає (фінальна_сітка, час).
    Кожна частинка — окремий потік з власним RNG.
    """
    from simulation import Crystal
    crystal = Crystal(grid_size)

    # Ініціалізація частинок — детермінована через seed
    positions = []
    for pid in range(n_particles):
        init_rng = random.Random(master_seed + pid * 10000)
        r, c = init_rng.randrange(grid_size), init_rng.randrange(grid_size)
        crystal.grid[r][c] += 1
        positions.append([r, c])

    barrier = threading.Barrier(n_particles + 1)

    def worker(pid: int):
        # Власний RNG — незалежний від усіх інших потоків
        rng = random.Random(master_seed + pid)
        pos = positions[pid]
        for _ in range(n_steps):
            r = rng.random()
            if r < 0.25:    dr, dc = -1, 0
            elif r < 0.50:  dr, dc = 1, 0
            elif r < 0.75:  dr, dc = 0, -1
            else:            dr, dc = 0, 1

            nr = max(0, min(grid_size - 1, pos[0] + dr))
            nc = max(0, min(grid_size - 1, pos[1] + dc))
            crystal.move_particle(pos[0], pos[1], nr, nc)
            pos[0], pos[1] = nr, nc

            barrier.wait()   # синхронізація між кроками
            barrier.wait()

    threads = [threading.Thread(target=worker, args=(pid,), daemon=True)
               for pid in range(n_particles)]

    t0 = time.perf_counter()
    for t in threads: t.start()

    # Головний потік — просто пропускає через бар'єри
    for _ in range(n_steps):
        barrier.wait()
        barrier.wait()

    for t in threads: t.join()
    elapsed = time.perf_counter() - t0

    return crystal.get_snapshot(), elapsed


def demonstrate_reproducibility() -> dict:
    """
    Запускає два ідентичних прогони і порівнює результати.
    """
    SEED = config.MASTER_SEED
    G, N, S = 20, 50, 200

    print("  [seed demo] Запуск 1...")
    grid1, t1 = run_reproducible(SEED, G, N, S)
    print("  [seed demo] Запуск 2...")
    grid2, t2 = run_reproducible(SEED, G, N, S)

    identical = (grid1 == grid2)

    # Підрахуємо кількість клітинок що збіглися
    matches = sum(grid1[r][c] == grid2[r][c]
                  for r in range(G) for c in range(G))
    total_cells = G * G

    return {
        "mode": "reproducibility_demo",
        "master_seed": SEED,
        "grid_size": G,
        "n_particles": N,
        "n_steps": S,
        "run1_elapsed_s": round(t1, 3),
        "run2_elapsed_s": round(t2, 3),
        "grids_identical": identical,
        "matching_cells": matches,
        "total_cells": total_cells,
        "match_pct": round(matches / total_cells * 100, 1),
    }
