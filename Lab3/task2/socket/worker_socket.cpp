// worker_socket.cpp — C++ worker, TCP-сокет (loopback).
// Підключається до Python main як клієнт.
//
// Компіляція Windows (MinGW):
//   g++ -O2 -std=c++17 worker_socket.cpp -o worker_socket.exe -lws2_32
// Компіляція Linux:
//   g++ -O2 -std=c++17 worker_socket.cpp -o worker_socket

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#ifdef _WIN32
  #include <winsock2.h>
  #include <ws2tcpip.h>
  #pragma comment(lib, "ws2_32.lib")   // для MSVC; MinGW — додати -lws2_32
  typedef int socklen_t;
  #define SOCK_ERR  SOCKET_ERROR
  #define CLOSE(s)  closesocket(s)
  static void init_winsock() {
      WSADATA w;
      if (WSAStartup(MAKEWORD(2, 2), &w) != 0) {
          fprintf(stderr, "WSAStartup failed\n"); exit(1);
      }
  }
#else
  #include <arpa/inet.h>
  #include <netinet/tcp.h>
  #include <sys/socket.h>
  #include <unistd.h>
  #define SOCK_ERR  (-1)
  #define CLOSE(s)  close(s)
  #define SOCKET    int
  static void init_winsock() {}   // no-op на Linux
#endif

// Надійне читання n байт із сокета
static bool recv_all(SOCKET s, void* dst, int n) {
    char* p = static_cast<char*>(dst);
    int got = 0;
    while (got < n) {
        int r = recv(s, p + got, n - got, 0);
        if (r <= 0) return false;
        got += r;
    }
    return true;
}

// Надійне надсилання n байт
static bool send_all(SOCKET s, const void* src, int n) {
    const char* p = static_cast<const char*>(src);
    int sent = 0;
    while (sent < n) {
        int r = send(s, p + sent, n - sent, 0);
        if (r <= 0) return false;
        sent += r;
    }
    return true;
}

int main(int argc, char** argv) {
    int port = (argc > 1) ? atoi(argv[1]) : 9877;
    init_winsock();

    SOCKET s = socket(AF_INET, SOCK_STREAM, 0);
    if (s == (SOCKET)SOCK_ERR) {
        fprintf(stderr, "[cpp-socket] socket() failed\n"); return 1;
    }

    // TCP_NODELAY — вимикає алгоритм Nagle, критично для маленьких пакетів
    int one = 1;
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY,
               reinterpret_cast<const char*>(&one), sizeof(one));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port   = htons((uint16_t)port);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    // Повторні спроби підключення (Python може ще не відкрити listen)
    bool connected = false;
    for (int i = 0; i < 50; i++) {
        if (connect(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0) {
            connected = true; break;
        }
#ifdef _WIN32
        Sleep(20);
#else
        usleep(20000);
#endif
    }
    if (!connected) {
        fprintf(stderr, "[cpp-socket] connect to 127.0.0.1:%d failed\n", port);
        return 1;
    }
    fprintf(stderr, "[cpp-socket] connected to 127.0.0.1:%d\n", port);

    int32_t val;
    int counter = 0;
    while (recv_all(s, &val, sizeof(val))) {
        if (counter % 1000 == 0) {
            fprintf(stderr, "[cpp-socket] LOG #%d: value=%d\n", counter, val);
            fflush(stderr);
        }
        counter++;
        int32_t back = val * 2;
        if (!send_all(s, &back, sizeof(back))) break;
    }

    fprintf(stderr, "[cpp-socket] exit, processed=%d\n", counter);
    CLOSE(s);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
