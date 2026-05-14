"""
simulation.py — безпечна симуляція броунівського руху.

Кожна частинка — окремий потік.
Складна задача A: кожна частинка має власний RNG з seed = MASTER_SEED + particle_id,
що забезпечує повну відтворюваність незалежно від порядку виконання потоків.

Синхронізація:
  - per-cell Lock: кожна клітинка сітки захищена своїм мютексом.
    Потік захоплює лок SOURCE-клітинки, потім DESTINATION (у порядку
    зростання індексу — lock ordering, щоб уникнути deadlock).
  - Barrier між кроками: всі частинки чекають одна одну перед наступним кроком.
    Це гарантує коректність знімків: знімок робиться тільки коли всі частинки
    завершили поточний крок.
"""
import threading
import random
import time
from typing import List, Tuple, Optional
import config


class Crystal:
    """Двовимірна сітка N×N. Зберігає кількість частинок у кожній клітинці."""

    def __init__(self, size: int):
        self.size = size
        # grid[row][col] = кількість частинок
        self.grid = [[0] * size for _ in range(size)]
        # Per-cell lock: lock_grid[row][col]
        self.lock_grid = [[threading.Lock() for _ in range(size)]
                          for _ in range(size)]

    def get_snapshot(self) -> List[List[int]]:
        """Повертає глибоку копію сітки — безпечний знімок."""
        return [row[:] for row in self.grid]

    def count_particles(self) -> int:
        return sum(self.grid[r][c]
                   for r in range(self.size)
                   for c in range(self.size))

    def _cell_index(self, row: int, col: int) -> int:
        """Лінійний індекс клітинки — використовується для lock ordering."""
        return row * self.size + col

    def move_particle(self, src_row: int, src_col: int,
                      dst_row: int, dst_col: int) -> bool:
        """
        Атомарно переміщує одну частинку з src у dst.
        Lock ordering: захоплюємо лок з меншим індексом першим — це унеможливлює
        deadlock при зустрічних переміщеннях між тими самими двома клітинками.
        Повертає True якщо переміщення відбулось.
        """
        src_idx = self._cell_index(src_row, src_col)
        dst_idx = self._cell_index(dst_row, dst_col)

        if src_idx == dst_idx:
            return True  # відбиття від межі — залишаємось на місці

        # Завжди захоплюємо у порядку зростання індексу
        first_row, first_col, second_row, second_col = (
            (src_row, src_col, dst_row, dst_col)
            if src_idx < dst_idx
            else (dst_row, dst_col, src_row, src_col)
        )

        with self.lock_grid[first_row][first_col]:
            with self.lock_grid[second_row][second_col]:
                if self.grid[src_row][src_col] <= 0:
                    return False  # частинки вже нема (не повинно траплятись)
                self.grid[src_row][src_col] -= 1
                self.grid[dst_row][dst_col] += 1
                return True


class Particle:
    """Частинка з власним RNG (задача A — відтворюваність)."""

    def __init__(self, particle_id: int, crystal: Crystal):
        self.id = particle_id
        self.crystal = crystal
        size = crystal.size

        # Початкова позиція — рівномірно по сітці, детермінована через seed
        init_rng = random.Random(config.MASTER_SEED + particle_id * 10000)
        self.row = init_rng.randrange(size)
        self.col = init_rng.randrange(size)

        # Власний RNG частинки — незалежний від інших потоків
        # seed = MASTER_SEED + particle_id, тому при однаковому MASTER_SEED
        # траєкторія кожної частинки повністю відтворювана
        self.rng = random.Random(config.MASTER_SEED + particle_id)

    def step(self) -> Tuple[int, int]:
        """Один крок руху. Повертає нову (row, col)."""
        r = self.rng.random()
        size = self.crystal.size

        if r < config.P_UP:
            dr, dc = -1, 0
        elif r < config.P_UP + config.P_DOWN:
            dr, dc = 1, 0
        elif r < config.P_UP + config.P_DOWN + config.P_LEFT:
            dr, dc = 0, -1
        else:
            dr, dc = 0, 1

        new_row = self.row + dr
        new_col = self.col + dc

        # Відбиття від меж: якщо виходимо за сітку — залишаємось на місці
        if not (0 <= new_row < size and 0 <= new_col < size):
            new_row, new_col = self.row, self.col

        self.crystal.move_particle(self.row, self.col, new_row, new_col)
        self.row, self.col = new_row, new_col
        return self.row, self.col


class SafeSimulation:
    """
    Повноцінна симуляція із:
    - per-particle thread
    - threading.Barrier між кроками (всі чекають перед наступним кроком)
    - знімки у потокобезпечні моменти (після бар'єру)
    - seed-based RNG для відтворюваності (задача A)
    """

    def __init__(self):
        self.crystal = Crystal(config.GRID_SIZE)
        self.particles: List[Particle] = []
        self.snapshots: List[Tuple[int, List[List[int]]]] = []  # (step, grid_copy)
        self._snapshot_lock = threading.Lock()

        # Статистика
        self.start_count: int = 0
        self.end_count: int = 0
        self.elapsed: float = 0.0

        # Barrier: всі N_PARTICLES потоків + 1 головний потік
        # Після кожного кроку потоки зустрічаються тут
        self._barrier = threading.Barrier(config.N_PARTICLES + 1)

        # Глобальний лічильник кроку (для знімків)
        self._current_step = 0
        self._step_lock = threading.Lock()

    def _init_particles(self):
        """Розміщуємо частинки на сітці."""
        for pid in range(config.N_PARTICLES):
            p = Particle(pid, self.crystal)
            self.particles.append(p)
            self.crystal.grid[p.row][p.col] += 1

    def _particle_worker(self, particle: Particle):
        """Функція потоку для однієї частинки."""
        for step in range(config.N_STEPS):
            # Один крок руху
            particle.step()

            # Зустрічаємось з усіма потоками + головним після кожного кроку
            # Головний потік тут робить знімок якщо потрібно
            self._barrier.wait()

            # Ще одна зустріч — чекаємо поки головний потік закінчить знімок
            self._barrier.wait()

    def _main_coordinator(self):
        """Головний потік-координатор: робить знімки між кроками."""
        for step in range(config.N_STEPS):
            # Перший бар'єр: чекаємо завершення кроку всіма частинками
            self._barrier.wait()

            # Тут всі частинки завершили крок — знімок консистентний
            self._current_step = step + 1
            if (step + 1) % config.SNAPSHOT_EVERY == 0 or step == 0:
                snap = self.crystal.get_snapshot()
                with self._snapshot_lock:
                    self.snapshots.append((step + 1, snap))

            # Другий бар'єр: відпускаємо частинки на наступний крок
            self._barrier.wait()

    def run(self) -> dict:
        """Запускає симуляцію, повертає словник з результатами."""
        self._init_particles()
        self.start_count = self.crystal.count_particles()

        # Знімок нульового стану (до старту)
        self.snapshots.append((0, self.crystal.get_snapshot()))

        threads = [
            threading.Thread(target=self._particle_worker, args=(p,), daemon=True)
            for p in self.particles
        ]

        t0 = time.perf_counter()
        for t in threads:
            t.start()

        # Головний потік координує знімки
        self._main_coordinator()

        for t in threads:
            t.join()

        self.elapsed = time.perf_counter() - t0
        self.end_count = self.crystal.count_particles()

        return {
            "mode": "safe",
            "grid_size": config.GRID_SIZE,
            "n_particles": config.N_PARTICLES,
            "n_steps": config.N_STEPS,
            "master_seed": config.MASTER_SEED,
            "start_count": self.start_count,
            "end_count": self.end_count,
            "particle_conserved": self.start_count == self.end_count,
            "n_snapshots": len(self.snapshots),
            "elapsed_s": round(self.elapsed, 3),
        }
