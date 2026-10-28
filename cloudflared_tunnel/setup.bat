@echo off
title 安答 · Cloudflare 隧道首次初始化（只需跑一次）

REM ===== 首次初始化：登录 Cloudflare -> 创建隧道 -> 绑定域名 =====
REM 第1步 login：弹浏览器登录你的 Cloudflare 账号，选择托管 anda.dpdns.org 的域名授权
REM 第2步 create：创建名为 anda 的命名隧道（凭证自动存在 C:\Users\你\.cloudflared\）
REM 第3步 route dns：自动给 anda.dpdns.org 建 CNAME 指向这条隧道
REM   如果你已在 Cloudflare 控制台手动建过 CNAME，这步会提示 already exists——正常，说明绑好了

where cloudflared >nul 2>nul
if errorlevel 1 (
  echo [X] 没找到 cloudflared，先安装：winget install --id Cloudflare.cloudflared
  pause
  exit /b 1
)

echo [1/3] 弹出浏览器登录 Cloudflare ...
cloudflared tunnel login
if errorlevel 1 ( echo [X] 登录失败 & pause & exit /b 1 )

echo [2/3] 创建隧道 anda ...
cloudflared tunnel create anda

echo [3/3] 把域名 anda.dpdns.org 绑到隧道 ...
cloudflared tunnel route dns anda anda.dpdns.org

echo.
echo [OK] 初始化完成！
echo 日常使用顺序：python -m Backend.app  +  前端 npm run dev  +  双击 start.bat
echo 然后浏览器访问 https://anda.dpdns.org 验证
pause
