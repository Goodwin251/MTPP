// worker_pipe.cpp — C++ worker, обмін через stdin/stdout (pipe).
// Python запускає цей процес через subprocess.Popen(stdin=PIPE, stdout=PIPE).
//
// Компіляція Windows (MinGW):
//   g++ -O2 -std=c++17 worker_pipe.cpp -o worker_pipe.exe
// Компіляція Linux:
//   g++ -O2 -std=c++17 worker_pipe.cpp -o worker_pipe

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#ifdef _WIN32
  #include <fcntl.h>   // _O_BINARY
  #include <io.h>      // _setmode, _fileno
#else
  #include <unistd.h>
#endif

// Читаємо рівно n байт. Повертаємо false при EOF або помилці.
static bool read_all(void* dst, size_t n) {
    size_t got = 0;
    while (got < n) {
        int c = fread(static_cast<char*>(dst) + got, 1, n - got, stdin);
        if (c <= 0) return false;
        got += c;
    }
    return true;
}

// Пишемо рівно n байт.
static bool write_all(const void* src, size_t n) {
    size_t sent = 0;
    while (sent < n) {
        int c = fwrite(static_cast<const char*>(src) + sent, 1, n - sent, stdout);
        if (c <= 0) return false;
        sent += c;
    }
    fflush(stdout);
    return true;
}

int main() {
#ifdef _WIN32
    // КРИТИЧНО на Windows: без binary-режиму 0x0A → 0x0D0A, дані псуються
    _setmode(_fileno(stdin),  _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif

    fprintf(stderr, "[cpp-pipe] worker started\n");
    fflush(stderr);

    int32_t val;
    int counter = 0;
    while (read_all(&val, sizeof(val))) {
        // [LOG] — логуємо кожне 1000-те (вимога завдання)
        if (counter % 1000 == 0) {
            fprintf(stderr, "[cpp-pipe] LOG #%d: value=%d\n", counter, val);
            fflush(stderr);
        }
        counter++;
        int32_t back = val * 2;
        if (!write_all(&back, sizeof(back))) break;
    }

    fprintf(stderr, "[cpp-pipe] worker exit, processed=%d\n", counter);
    return 0;
}
