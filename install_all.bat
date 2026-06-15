@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title DataAnalysis-Agent 一键安装

echo.
echo ========================================
echo   DataAnalysis-Agent 一键安装
echo ========================================
echo.

:: ============================================================
:: 1. 检查 Python
:: ============================================================
echo [1/5] 检查 Python 环境...

set "PYTHON="

for /f "tokens=*" %%i in ('where python3 2^>nul') do (
    set "PYTHON=%%i"
    goto :found_python
)
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    set "PYTHON=%%i"
    goto :found_python
)

:found_python
if "!PYTHON!"=="" (
    echo   [错误] 未找到 Python，请先安装 Python 3.12+
    echo   下载: https://www.python.org/downloads/
    echo   安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo   找到: !PYTHON!

"!PYTHON!" -c "import sys; print(sys.version.split()[0])" > "%TEMP%\py_ver_temp.txt" 2>&1
set /p PY_VER=<"%TEMP%\py_ver_temp.txt"
del "%TEMP%\py_ver_temp.txt" 2>nul
echo   Python 版本: !PY_VER!

for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)
if !PY_MAJOR! LSS 3 (echo   [错误] 需要 Python 3.12+ & pause & exit /b 1)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 12 (echo   [错误] 当前 !PY_VER!，需要 3.12+ & pause & exit /b 1)
echo   [通过]
echo.

:: ============================================================
:: 2. 创建虚拟环境
:: ============================================================
echo [2/5] 创建虚拟环境...
set "AGENT_DIR=%~dp0"
cd /d "!AGENT_DIR!"

if exist ".venv\Scripts\python.exe" (
    echo   虚拟环境已存在，跳过。
) else (
    if exist ".venv" rmdir /s /q ".venv"
    "!PYTHON!" -m venv .venv
    if errorlevel 1 (echo   [错误] 创建失败 & pause & exit /b 1)
    echo   [完成]
)
echo.

:: ============================================================
:: 3. 安装依赖
:: ============================================================
echo [3/5] 安装 Python 依赖...
.\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet 2>nul
.\.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (echo   [错误] 安装失败，请检查网络 & pause & exit /b 1)
echo   [完成]
echo.

:: ============================================================
:: 4. 安装 Playwright 浏览器
:: ============================================================
echo [4/5] 安装 Playwright 浏览器（~180MB，请耐心等待）...
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
.\.venv\Scripts\python.exe -m playwright install --force chromium
if errorlevel 1 (
    echo   [警告] 浏览器安装失败，排片预测功能将不可用
    echo          手动安装: .venv\Scripts\playwright install chromium
)
echo.

:: ============================================================
:: 5. 配置 .env
:: ============================================================
echo [5/5] 配置凭证...
cd /d "!AGENT_DIR!"

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
    ) else (
        (
            echo # 飞书应用凭证
            echo FEISHU_APP_ID=
            echo FEISHU_APP_SECRET=
            echo.
            echo # DeepSeek API
            echo DEEPSEEK_API_KEY=
            echo DEEPSEEK_BASE_URL=https://api.deepseek.com
            echo DEEPSEEK_MODEL=deepseek-chat
            echo.
            echo # LLM 参数
            echo LLM_TEMPERATURE=0.1
            echo LLM_MAX_TOKENS=800
            echo LLM_TIMEOUT=15
            echo.
            echo # Session 超时（秒）
            echo SESSION_TIMEOUT=600
            echo.
            echo # 日志级别
            echo LOG_LEVEL=INFO
        ) > ".env"
    )
    echo.
    echo   ========================================
    echo   .env 模板已创建，请填入三个凭证：
    echo   ========================================
    echo.
    echo   1. FEISHU_APP_ID      — 飞书应用 App ID
    echo   2. FEISHU_APP_SECRET  — 飞书应用 App Secret
    echo   3. DEEPSEEK_API_KEY   — DeepSeek API Key
    echo.
    echo   是否现在打开 .env 编辑？[Y/N]
    set /p "OPEN_ENV="
    if /i "!OPEN_ENV!"=="Y" start notepad ".env"
    echo.
) else (
    echo   .env 已存在，跳过。
    echo.
)

:: ============================================================
:: 完成
:: ============================================================
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo   启动: 双击 start.vbs，或运行 .venv\Scripts\python main.py
echo   验证: .venv\Scripts\python test_agent.py
echo.
pause
