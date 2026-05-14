@echo off
echo === Компіляція C++ воркерів ===

echo [1/3] Pipe...
g++ -O2 -std=c++17 pipe\worker_pipe.cpp -o pipe\worker_pipe.exe
if errorlevel 1 ( echo FAILED: pipe & exit /b 1 )
echo   OK: pipe\worker_pipe.exe

echo [2/3] Socket...
g++ -O2 -std=c++17 socket\worker_socket.cpp -o socket\worker_socket.exe -lws2_32
if errorlevel 1 ( echo FAILED: socket & exit /b 1 )
echo   OK: socket\worker_socket.exe

echo [3/3] Shared Memory...
g++ -O2 -std=c++17 shared_mem\worker_shm.cpp -o shared_mem\worker_shm.exe
if errorlevel 1 ( echo FAILED: shared_mem & exit /b 1 )
echo   OK: shared_mem\worker_shm.exe

echo.
echo === Всі воркери скомпільовано ===
echo Запуск: python run_all.py --n 50000
