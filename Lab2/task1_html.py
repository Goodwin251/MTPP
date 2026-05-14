"""
Задача 1.1: Підрахунок частоти HTML-тегів у наборі документів.

Реалізації:
  - sequential: послідовний обхід усіх файлів.
  - Map-Reduce: розподілити файли по worker-ах (map), злити Counter (reduce).
  - Fork-Join: рекурсивний поділ списку файлів навпіл до порогового розміру.
  - Worker Pool: фіксований пул процесів, які беруть файли з черги.

Файли читаємо у воркерах — не передаємо вміст через pickle, лише шляхи.
"""
import os
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

TAG_RE = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9]*)", re.ASCII)


def count_tags_in_file(path: str) -> Counter:
    """Підрахунок тегів в одному HTML-файлі."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return Counter(m.lower() for m in TAG_RE.findall(text))


def count_tags_in_chunk(paths):
    """Підрахунок по списку файлів — повертає об'єднаний Counter."""
    result = Counter()
    for p in paths:
        result.update(count_tags_in_file(p))
    return result


# ---------- Sequential ----------
def run_sequential(paths):
    result = Counter()
    for p in paths:
        result.update(count_tags_in_file(p))
    return result


# ---------- Map-Reduce ----------
def run_map_reduce(paths, n_workers: int):
    # map: розбиваємо файли на n_workers рівних частин
    chunk_size = max(1, len(paths) // n_workers)
    chunks = [paths[i:i + chunk_size] for i in range(0, len(paths), chunk_size)]
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        partial = list(ex.map(count_tags_in_chunk, chunks))
    # reduce: злиття Counter-ів
    total = Counter()
    for c in partial:
        total.update(c)
    return total


# ---------- Fork-Join ----------
# Класичний fork-join: рекурсивний поділ списку файлів навпіл до порога.
# Рекурсивний поділ виконуємо в головному процесі — формуємо плоский список
# листових частин. Усі листки паралельно обробляються у пулі процесів,
# потім результати ієрархічно зливаються попарно.
FORK_THRESHOLD = 50  # якщо файлів менше — листок (обробляємо як одну задачу)


def _build_chunks(paths):
    if len(paths) <= FORK_THRESHOLD:
        return [paths]
    mid = len(paths) // 2
    return _build_chunks(paths[:mid]) + _build_chunks(paths[mid:])


def run_fork_join(paths, n_workers: int):
    chunks = _build_chunks(paths)
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        partial = list(ex.map(count_tags_in_chunk, chunks))
    # join: ієрархічне попарне злиття
    while len(partial) > 1:
        merged = []
        for i in range(0, len(partial), 2):
            if i + 1 < len(partial):
                a = partial[i]; a.update(partial[i + 1])
                merged.append(a)
            else:
                merged.append(partial[i])
        partial = merged
    return partial[0] if partial else Counter()


# ---------- Worker Pool ----------
def _worker_pool_worker(in_q: mp.Queue, out_q: mp.Queue):
    """Воркер: бере шляхи з черги, кладе Counter в out_q. Sentinel = None."""
    local = Counter()
    while True:
        item = in_q.get()
        if item is None:
            out_q.put(local)
            return
        local.update(count_tags_in_file(item))


def run_worker_pool(paths, n_workers: int):
    in_q = mp.Queue(maxsize=n_workers * 4)
    out_q = mp.Queue()
    workers = [mp.Process(target=_worker_pool_worker, args=(in_q, out_q))
               for _ in range(n_workers)]
    for w in workers:
        w.start()
    for p in paths:
        in_q.put(p)
    for _ in range(n_workers):
        in_q.put(None)
    total = Counter()
    for _ in range(n_workers):
        total.update(out_q.get())
    for w in workers:
        w.join()
    return total


def collect_paths(html_dir: str):
    return sorted(
        os.path.join(html_dir, f) for f in os.listdir(html_dir)
        if f.endswith(".html")
    )
