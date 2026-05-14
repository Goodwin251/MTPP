// worker_shm.cpp — C++ worker, Shared Memory.
// Windows: CreateFileMapping / MapViewOfFile
// Linux:   shm_open / mmap
//
// Компіляція Windows (MinGW):
//   g++ -O2 -std=c++17 worker_shm.cpp -o worker_shm.exe
// Компіляція Linux:
//   g++ -O2 -std=c++17 worker_shm.cpp -o worker_shm -lrt

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

// ── Платформо-залежні заголовки ───────────────────────────────────────────

#ifdef _WIN32
  #include <windows.h>
  // На Windows "shared memory" = named file mapping у pagefile
  static HANDLE   g_map  = nullptr;
  static void*    g_view = nullptr;

  static void* shm_open_win(const char* name, size_t size) {
      g_map = CreateFileMappingA(
          INVALID_HANDLE_VALUE,   // pagefile-backed
          nullptr,
          PAGE_READWRITE,
          0, (DWORD)size,
          name                    // глобальна назва "lab3_shm"
      );
      if (!g_map) {
          // Якщо main ще не створив — чекаємо
          for (int i = 0; i < 100; i++) {
              Sleep(20);
              g_map = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name);
              if (g_map) break;
          }
      }
      if (!g_map) { fprintf(stderr, "[cpp-shm] OpenFileMapping failed\n"); exit(1); }
      g_view = MapViewOfFile(g_map, FILE_MAP_ALL_ACCESS, 0, 0, size);
      if (!g_view) { fprintf(stderr, "[cpp-shm] MapViewOfFile failed\n"); exit(1); }
      return g_view;
  }

  static void shm_close_win() {
      if (g_view) UnmapViewOfFile(g_view);
      if (g_map)  CloseHandle(g_map);
  }

#else
  #include <fcntl.h>
  #include <sys/mman.h>
  #include <unistd.h>
  static int  g_fd   = -1;
  static void* g_ptr = nullptr;
  static size_t g_sz = 0;

  static void* shm_open_posix(const char* name, size_t size) {
      // чекаємо поки main створить сегмент
      for (int i = 0; i < 100; i++) {
          g_fd = shm_open(name, O_RDWR, 0666);
          if (g_fd >= 0) break;
          usleep(20000);
      }
      if (g_fd < 0) { perror("shm_open"); exit(1); }
      g_sz  = size;
      g_ptr = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, g_fd, 0);
      if (g_ptr == MAP_FAILED) { perror("mmap"); exit(1); }
      return g_ptr;
  }

  static void shm_close_posix() {
      if (g_ptr && g_ptr != MAP_FAILED) munmap(g_ptr, g_sz);
      if (g_fd >= 0) close(g_fd);
  }
#endif

// ── Структура спільного блоку (16 байт) ─────────────────────────────────
// offset 0:  int32  seq      — main інкрементує (новий запит)
// offset 4:  int32  ack      — worker інкрементує (оброблено)
// offset 8:  int32  val_in   — число від main
// offset 12: int32  val_out  — відповідь worker

static inline int32_t read32 (const char* base, int off) {
    int32_t v; memcpy(&v, base + off, 4); return v;
}
static inline void   write32(char* base, int off, int32_t v) {
    memcpy(base + off, &v, 4);
}

int main(int argc, char** argv) {
    const char* name = (argc > 1) ? argv[1] : "lab3_shm";
    const size_t SZ  = 16;

    fprintf(stderr, "[cpp-shm] opening shared memory '%s'\n", name);
    fflush(stderr);

#ifdef _WIN32
    char* base = static_cast<char*>(shm_open_win(name, SZ));
#else
    char* base = static_cast<char*>(shm_open_posix(name, SZ));
#endif

    fprintf(stderr, "[cpp-shm] mapped OK\n");
    fflush(stderr);

    int32_t last_seq = 0;
    int counter = 0;

    while (true) {
        int32_t cur_seq = read32(base, 0);
        if (cur_seq < 0) break;   // сигнал завершення від main

        if (cur_seq != last_seq) {
            int32_t val = read32(base, 8);

            if (counter % 1000 == 0) {
                fprintf(stderr, "[cpp-shm] LOG #%d: value=%d\n", counter, val);
                fflush(stderr);
            }
            counter++;

            write32(base, 12, val * 2);   // val_out
            // Повна пам'ять-бар'єр перед записом ack
            std::atomic_thread_fence(std::memory_order_seq_cst);
            write32(base, 4, cur_seq);    // ack = seq

            last_seq = cur_seq;
        } else {
            // Мікросон щоб не жерти 100% CPU в spin-wait
#ifdef _WIN32
            Sleep(0);   // yield квант Windows scheduler
#else
            usleep(10);
#endif
        }
    }

    fprintf(stderr, "[cpp-shm] exit, processed=%d\n", counter);

#ifdef _WIN32
    shm_close_win();
#else
    shm_close_posix();
#endif
    return 0;
}
