"""
Задача 1.2: Знайти min, max, median, mean масиву > 1 000 000 чисел.

Реалізації:
  - sequential: numpy на повному масиві.
  - Map-Reduce: розбити масив на блоки, у кожному порахувати локальні
    мінімум/максимум/суму/довжину/відсортований блок; reduce — звести.
    Медіану рахуємо через об'єднання відсортованих блоків.
  - Fork-Join: рекурсивний поділ до порога.
  - Worker Pool: пул процесів отримує блоки з черги.

Особливість: масив передаємо через shared memory (SharedMemory),
бо pickle-серіалізація 2M float'ів між процесами дорога.
"""
import numpy as np
from multiprocessing import shared_memory
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


def stats_block(arr_block: np.ndarray):
    """Часткова статистика блоку: min, max, sum, count, sorted-copy."""
    return {
        "min": float(arr_block.min()),
        "max": float(arr_block.max()),
        "sum": float(arr_block.sum()),
        "count": int(arr_block.size),
        "sorted": np.sort(arr_block),
    }


def _stats_from_shm(shm_name: str, shape, dtype, start: int, end: int):
    shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
    res = stats_block(arr[start:end])
    shm.close()
    return res


def _merge_partial(parts):
    """Зведення часткових статистик. Медіану рахуємо точно — через
    об'єднання вже відсортованих блоків (merge відсортованих масивів)."""
    mn = min(p["min"] for p in parts)
    mx = max(p["max"] for p in parts)
    total = sum(p["sum"] for p in parts)
    cnt = sum(p["count"] for p in parts)
    mean = total / cnt
    # Точна медіана: конкатенуємо відсортовані блоки і ще раз сортуємо.
    # (np.sort вже близько до лінійного на майже відсортованих даних.)
    merged = np.concatenate([p["sorted"] for p in parts])
    merged.sort()
    if cnt % 2 == 1:
        median = float(merged[cnt // 2])
    else:
        median = float(0.5 * (merged[cnt // 2 - 1] + merged[cnt // 2]))
    return {"min": mn, "max": mx, "mean": mean, "median": median}


# ---------- Sequential ----------
def run_sequential(arr: np.ndarray):
    return {
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
    }


# ---------- Спільна частина: shared memory ----------
def _make_shared(arr: np.ndarray):
    shm = shared_memory.SharedMemory(create=True, size=arr.nbytes)
    buf = np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)
    buf[:] = arr[:]
    return shm


def _close_shared(shm):
    shm.close()
    shm.unlink()


# ---------- Map-Reduce ----------
def run_map_reduce(arr: np.ndarray, n_workers: int):
    shm = _make_shared(arr)
    try:
        n = arr.size
        chunk = n // n_workers
        ranges = [(i * chunk, n if i == n_workers - 1 else (i + 1) * chunk)
                  for i in range(n_workers)]
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futures = [ex.submit(_stats_from_shm, shm.name, arr.shape,
                                 arr.dtype, s, e) for s, e in ranges]
            parts = [f.result() for f in futures]
        return _merge_partial(parts)
    finally:
        _close_shared(shm)


# ---------- Fork-Join ----------
# Класичний fork-join: рекурсивний поділ задачі. Рекурсію виконуємо в
# головному процесі — формуємо плоский список листових діапазонів, паралельно
# обчислюємо статистики листків, потім ієрархічно (попарно) зводимо їх назад.
# Це коректний fork-join: дерево поділу будується явно, "fork" = submit
# листкових задач у пул, "join" = попарне злиття результатів від листя до кореня.
FORK_THRESHOLD = 200_000

def _build_leaves(start: int, end: int):
    """Будуємо плоский список діапазонів-листя через рекурсивний поділ."""
    if end - start <= FORK_THRESHOLD:
        return [(start, end)]
    mid = (start + end) // 2
    return _build_leaves(start, mid) + _build_leaves(mid, end)


def _merge_two(a, b):
    """Об'єднання двох часткових статистик (без обчислення фінальної медіани)."""
    merged_sorted = np.concatenate([a["sorted"], b["sorted"]])
    merged_sorted.sort()
    return {
        "min": min(a["min"], b["min"]),
        "max": max(a["max"], b["max"]),
        "sum": a["sum"] + b["sum"],
        "count": a["count"] + b["count"],
        "sorted": merged_sorted,
    }


def run_fork_join(arr: np.ndarray, n_workers: int):
    shm = _make_shared(arr)
    try:
        leaves = _build_leaves(0, arr.size)
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futures = [ex.submit(_stats_from_shm, shm.name, arr.shape,
                                 arr.dtype, s, e) for s, e in leaves]
            parts = [f.result() for f in futures]
        # Ієрархічне попарне злиття (join) — імітує підйом по дереву
        while len(parts) > 1:
            merged = []
            for i in range(0, len(parts), 2):
                if i + 1 < len(parts):
                    merged.append(_merge_two(parts[i], parts[i + 1]))
                else:
                    merged.append(parts[i])
            parts = merged
        return _merge_partial(parts)
    finally:
        _close_shared(shm)


# ---------- Worker Pool ----------
def _wp_worker(shm_name, shape, dtype, in_q, out_q):
    shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
    while True:
        rng = in_q.get()
        if rng is None:
            break
        s, e = rng
        out_q.put(stats_block(arr[s:e]))
    shm.close()


def run_worker_pool(arr: np.ndarray, n_workers: int, n_chunks: int = None):
    shm = _make_shared(arr)
    try:
        if n_chunks is None:
            n_chunks = n_workers * 2
        n = arr.size
        chunk = n // n_chunks
        ranges = [(i * chunk, n if i == n_chunks - 1 else (i + 1) * chunk)
                  for i in range(n_chunks)]
        in_q = mp.Queue()
        out_q = mp.Queue()
        workers = [mp.Process(target=_wp_worker,
                              args=(shm.name, arr.shape, arr.dtype, in_q, out_q))
                   for _ in range(n_workers)]
        for w in workers:
            w.start()
        for r in ranges:
            in_q.put(r)
        for _ in range(n_workers):
            in_q.put(None)
        parts = [out_q.get() for _ in ranges]
        for w in workers:
            w.join()
        return _merge_partial(parts)
    finally:
        _close_shared(shm)
