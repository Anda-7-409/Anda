@echo off
title 安答 · Cloudflare Tunnel

REM ===== 日常启动脚本：公网 https://anda.dpdns.org -> 本地 Vite(5173) =====
REM 前提：后端(python -m Backend.app) 和前端(npm run dev) 已照常启动，本脚本只负责"穿墙"
REM 用法：双击运行，看到 Registered tunnel connection 字样即成功；Ctrl+C 停止隧道
REM 首次使用请先双击 setup.bat 完成登录和域名绑定

where cloudflared >nul 2>nul
if errorlevel 1 (
  echo [X] 没找到 cloudflared，先安装：winget install --id Cloudflare.cloudflared
  pause
  exit /b 1
)

echo [i] 正在启动隧道：anda.dpdns.org -^> http://localhost:5173 ...
echo [i] 启动成功后访问：https://anda.dpdns.org  （关闭本窗口或 Ctrl+C 即下线）
cloudflared tunnel run --url http://localhost:5173 anda
pause
