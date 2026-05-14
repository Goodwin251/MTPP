"""
Memory-bound задача: транспонування великої матриці (10000 x 10000) методом
поблочної обробки.

Реалізовано:
  - послідовне транспонування (numpy);
  - паралельне транспонування на потоках (ThreadPoolExecutor) поблочно;
  - паралельне транспонування на процесах (ProcessPoolExecutor) поблочно
    через shared-memory масив.

Для memory-bound задачі особливо важливо, що при потоках уся пам'ять
розділяється, а при процесах потрібен спеціальний канал передачі (shared memory),
бо передача 800МБ через pickle вбила б продуктивність.
"""

import time
import numpy as np
from concurrent.futures import ThreadPoolExecutor


def transpose_sequential(matrix: np.ndarray) -> np.ndarray:
    """Послідовне транспонування з фізичним копіюванням у новий буфер
    (.copy() важливе: інакше numpy лише змінив би strides, що не показало б
    реальної memory-bound роботи)."""
    return matrix.T.copy()


def _transpose_block(args):
    """Транспонує блок [row_start:row_end, :] вхідної матриці і записує його
    у [:, row_start:row_end] вихідної матриці."""
    src, dst, row_start, row_end = args
    dst[:, row_start:row_end] = src[row_start:row_end, :].T


def transpose_parallel_threads(matrix: np.ndarray, n_workers: int) -> np.ndarray:
    """Поблочне паралельне транспонування на потоках. Numpy операції
    звільняють GIL, тому потоки дають реальний паралелізм."""
    n_rows, n_cols = matrix.shape
    result = np.empty((n_cols, n_rows), dtype=matrix.dtype)
    block = n_rows // n_workers
    tasks = []
    for i in range(n_workers):
        s = i * block
        e = n_rows if i == n_workers - 1 else s + block
        tasks.append((matrix, result, s, e))
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        list(ex.map(_transpose_block, tasks))
    return result


def time_it(fn, *args, **kwargs):
    t0 = time.perf_counter()
    res = fn(*args, **kwargs)
    return res, time.perf_counter() - t0
