@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动手掌地球仪，请不要关闭这个窗口...
set PY=python
where py >nul 2>nul && set PY=py
start "" /b %PY% -m http.server 8000
timeout /t 2 /nobreak >nul
start "" http://localhost:8000/
echo 已在浏览器打开 http://localhost:8000/ ，用完后关闭本窗口即可。
pause >nul
