"""
Задача 1.3: Множення матриць великого розміру.

Реалізації:
  - sequential: numpy @ (BLAS-послідовний для контролю).
  - Map-Reduce: розбити матрицю A на горизонтальні смуги, кожен воркер
    рахує C[s:e] = A[s:e] @ B; reduce — конкатенація.
  - Fork-Join: рекурсивний поділ смуг навпіл до порога.
  - Worker Pool: пул воркерів з чергою смуг.

Передаємо матриці через shared memory.

Важливо: BLAS уже багатопотоковий усередині. Щоб порівняння було чесним,
у воркерах обмежуємо BLAS до 1 потоку (через env var, перед імпортом numpy
у воркері — встановлюємо в головному процесі до старту пулу).
"""
import numpy as np
from multiprocessing import shared_memory
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


def _multiply_strip_shm(a_name, a_shape, a_dtype,
                        b_name, b_shape, b_dtype,
                        out_name, out_shape, out_dtype,
                        row_start, row_end):
    a_shm = shared_memory.SharedMemory(name=a_name)
    b_shm = shared_memory.SharedMemory(name=b_name)
    o_shm = shared_memory.SharedMemory(name=out_name)
    A = np.ndarray(a_shape, dtype=a_dtype, buffer=a_shm.buf)
    B = np.ndarray(b_shape, dtype=b_dtype, buffer=b_shm.buf)
    OUT = np.ndarray(out_shape, dtype=out_dtype, buffer=o_shm.buf)
    OUT[row_start:row_end, :] = A[row_start:row_end, :] @ B
    a_shm.close(); b_shm.close(); o_shm.close()


def _make_shared(arr: np.ndarray):
    shm = shared_memory.SharedMemory(create=True, size=arr.nbytes)
    buf = np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)
    buf[:] = arr[:]
    return shm


def _close_shared(shm):
    shm.close()
    shm.unlink()


# ---------- Sequential ----------
def run_sequential(A: np.ndarray, B: np.ndarray):
    return A @ B


# ---------- Map-Reduce ----------
def run_map_reduce(A: np.ndarray, B: np.ndarray, n_workers: int):
    a_shm = _make_shared(A)
    b_shm = _make_shared(B)
    out = np.empty((A.shape[0], B.shape[1]), dtype=A.dtype)
    out_shm = _make_shared(out)
    try:
        rows = A.shape[0]
        chunk = rows // n_workers
        ranges = [(i * chunk, rows if i == n_workers - 1 else (i + 1) * chunk)
                  for i in range(n_workers)]
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futs = [ex.submit(_multiply_strip_shm,
                              a_shm.name, A.shape, A.dtype,
                              b_shm.name, B.shape, B.dtype,
                              out_shm.name, out.shape, out.dtype,
                              s, e) for s, e in ranges]
            for f in futs:
                f.result()
        result = np.ndarray(out.shape, dtype=out.dtype, buffer=out_shm.buf).copy()
        return result
    finally:
        _close_shared(a_shm); _close_shared(b_shm); _close_shared(out_shm)


# ---------- Fork-Join ----------
# Рекурсивний поділ виконуємо в головному процесі — будуємо плоский список
# листових смуг. Паралелізм досягається тим, що всі листки одночасно
# надсилаються до ProcessPoolExecutor. Це чесний fork-join: дерево поділу
# побудоване рекурсивно, листя обробляються паралельно.
FORK_THRESHOLD_ROWS = 128


def _build_row_leaves(start: int, end: int):
    if end - start <= FORK_THRESHOLD_ROWS:
        return [(start, end)]
    mid = (start + end) // 2
    return _build_row_leaves(start, mid) + _build_row_leaves(mid, end)


def run_fork_join(A: np.ndarray, B: np.ndarray, n_workers: int):
    a_shm = _make_shared(A)
    b_shm = _make_shared(B)
    out = np.empty((A.shape[0], B.shape[1]), dtype=A.dtype)
    out_shm = _make_shared(out)
    try:
        leaves = _build_row_leaves(0, A.shape[0])
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futs = [ex.submit(_multiply_strip_shm,
                              a_shm.name, A.shape, A.dtype,
                              b_shm.name, B.shape, B.dtype,
                              out_shm.name, out.shape, out.dtype,
                              s, e) for s, e in leaves]
            for f in futs:
                f.result()
        return np.ndarray(out.shape, dtype=out.dtype, buffer=out_shm.buf).copy()
    finally:
        _close_shared(a_shm); _close_shared(b_shm); _close_shared(out_shm)


# ---------- Worker Pool ----------
def _wp_worker(a_name, a_shape, a_dtype, b_name, b_shape, b_dtype,
               out_name, out_shape, out_dtype, in_q, done_q):
    a_shm = shared_memory.SharedMemory(name=a_name)
    b_shm = shared_memory.SharedMemory(name=b_name)
    o_shm = shared_memory.SharedMemory(name=out_name)
    A = np.ndarray(a_shape, dtype=a_dtype, buffer=a_shm.buf)
    B = np.ndarray(b_shape, dtype=b_dtype, buffer=b_shm.buf)
    OUT = np.ndarray(out_shape, dtype=out_dtype, buffer=o_shm.buf)
    while True:
        item = in_q.get()
        if item is None:
            break
        s, e = item
        OUT[s:e, :] = A[s:e, :] @ B
        done_q.put(1)
    a_shm.close(); b_shm.close(); o_shm.close()


def run_worker_pool(A: np.ndarray, B: np.ndarray, n_workers: int,
                    n_chunks: int = None):
    a_shm = _make_shared(A)
    b_shm = _make_shared(B)
    out = np.empty((A.shape[0], B.shape[1]), dtype=A.dtype)
    out_shm = _make_shared(out)
    try:
        if n_chunks is None:
            n_chunks = n_workers * 2
        rows = A.shape[0]
        chunk = rows // n_chunks
        ranges = [(i * chunk, rows if i == n_chunks - 1 else (i + 1) * chunk)
                  for i in range(n_chunks)]
        in_q = mp.Queue()
        done_q = mp.Queue()
        workers = [mp.Process(target=_wp_worker,
                              args=(a_shm.name, A.shape, A.dtype,
                                    b_shm.name, B.shape, B.dtype,
                                    out_shm.name, out.shape, out.dtype,
                                    in_q, done_q))
                   for _ in range(n_workers)]
        for w in workers:
            w.start()
        for r in ranges:
            in_q.put(r)
        for _ in range(n_workers):
            in_q.put(None)
        for _ in ranges:
            done_q.get()
        for w in workers:
            w.join()
        return np.ndarray(out.shape, dtype=out.dtype, buffer=out_shm.buf).copy()
    finally:
        _close_shared(a_shm); _close_shared(b_shm); _close_shared(out_shm)
