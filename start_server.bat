@echo off
REM AISleepGen 开机自启动 — 拉起 deepseek_proxy + SRE看护
REM 加到启动项: shell:startup → 放这个vbs

cd /d D:\AISleepGen_Optimized
start /B "" python deepseek_proxy.py
