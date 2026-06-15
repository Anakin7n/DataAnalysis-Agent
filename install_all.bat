@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title DataAnalysis-Agent 一键安装程序

echo.
echo ========================================
echo   DataAnalysis-Agent 一键安装程序
echo   安装：Agent + 3 个 Bot + 所有依赖
echo ========================================
echo.

:: ============================================================
:: Step 1: 检查 Python
:: ============================================================
echo [1/8] 检查 Python 环境...
echo.

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
    echo   下载地址: https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"
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

if "!PY_MAJOR!"=="" (
    echo   [错误] 无法检测 Python 版本
    pause
    exit /b 1
)

if !PY_MAJOR! LSS 3 (
    echo   [错误] Python 版本过低，需要 3.12+
    pause
    exit /b 1
)
if !PY_MAJOR! EQU 3 (
    if !PY_MINOR! LSS 12 (
        echo   [错误] Python 版本过低，当前 !PY_VER!，需要 3.12+
        pause
        exit /b 1
    )
)
echo   [通过] Python 版本符合要求
echo.

:: ============================================================
:: Step 2: 确定目录结构
:: ============================================================
echo [2/8] 检查项目目录结构...
echo.

:: 本脚本所在目录 = DataAnalysis-Agent
set "AGENT_DIR=%~dp0"
:: 父目录（所有项目应在此处）— "%~dp0.." 解析为 D:\
for %%i in ("%~dp0..") do set "PARENT_DIR=%%~fi"
if "!PARENT_DIR:~-1!"=="\" set "PARENT_DIR=!PARENT_DIR:~0,-1!"

set "REELCLEAN_DIR=!PARENT_DIR!\ReelClean-bot"
set "PREDICTION_DIR=!PARENT_DIR!\Prediction-Bot"
set "FEISHU_DIR=!PARENT_DIR!\feishu-bot"

if not exist "!REELCLEAN_DIR!" (
    echo   [警告] 未找到 ReelClean-bot 目录: !REELCLEAN_DIR!
    echo          请确保 ReelClean-bot 与本项目位于同一父目录
)
if not exist "!PREDICTION_DIR!" (
    echo   [警告] 未找到 Prediction-Bot 目录: !PREDICTION_DIR!
    echo          请确保 Prediction-Bot 与本项目位于同一父目录
)
if not exist "!FEISHU_DIR!" (
    echo   [警告] 未找到 feishu-bot 目录: !FEISHU_DIR!
    echo          请确保 feishu-bot 与本项目位于同一父目录
)
echo.

:: ============================================================
:: Step 3: 安装 ReelClean-bot
:: ============================================================
echo [3/8] 安装 ReelClean-bot（地面任务分析）...
echo.

if not exist "!REELCLEAN_DIR!" (
    echo   目录不存在，跳过。
    echo.
    goto :step4
)

cd /d "!REELCLEAN_DIR!"

call :install_bot_venv "ReelClean-bot" "!REELCLEAN_DIR!"
if errorlevel 1 (
    echo   [错误] ReelClean-bot 依赖安装失败
    echo.
) else (
    echo   [完成] ReelClean-bot 安装完成
    echo.
)

:: 基础 .env 模板
if not exist "!REELCLEAN_DIR!\.env" (
    echo FEISHU_APP_ID= > "!REELCLEAN_DIR!\.env"
    echo FEISHU_APP_SECRET= >> "!REELCLEAN_DIR!\.env"
    echo   [注意] 已创建 .env 模板，如需独立启动此 Bot，请填入飞书凭证
)

:step4

:: ============================================================
:: Step 4: 安装 Prediction-Bot
:: ============================================================
echo [4/8] 安装 Prediction-Bot（排片占比预测）...
echo.

if not exist "!PREDICTION_DIR!" (
    echo   目录不存在，跳过。
    echo.
    goto :step5
)

cd /d "!PREDICTION_DIR!"

call :install_bot_venv "Prediction-Bot" "!PREDICTION_DIR!"
if errorlevel 1 (
    echo   [错误] Prediction-Bot 依赖安装失败
    echo.
) else (
    echo   [完成] Prediction-Bot 安装完成
    echo.
)

if not exist "!PREDICTION_DIR!\.env" (
    if exist "!PREDICTION_DIR!\.env.example" (
        copy "!PREDICTION_DIR!\.env.example" "!PREDICTION_DIR!\.env" >nul 2>&1
    ) else (
        echo FEISHU_APP_ID= > "!PREDICTION_DIR!\.env"
        echo FEISHU_APP_SECRET= >> "!PREDICTION_DIR!\.env"
    )
    echo   [注意] 已创建 .env 模板，如需独立启动此 Bot，请填入飞书凭证
)

:step5

:: ============================================================
:: Step 5: 安装 feishu-bot
:: ============================================================
echo [5/8] 安装 feishu-bot（分时汇报）...
echo.

if not exist "!FEISHU_DIR!" (
    echo   目录不存在，跳过。
    echo.
    goto :step6
)

cd /d "!FEISHU_DIR!"

call :install_bot_venv "feishu-bot" "!FEISHU_DIR!"
if errorlevel 1 (
    echo   [错误] feishu-bot 依赖安装失败
    echo.
) else (
    echo   [完成] feishu-bot 安装完成
    echo.
)

if not exist "!FEISHU_DIR!\.env" (
    echo FEISHU_APP_ID= > "!FEISHU_DIR!\.env"
    echo FEISHU_APP_SECRET= >> "!FEISHU_DIR!\.env"
    echo   [注意] 已创建 .env 模板，如需独立启动此 Bot，请填入飞书凭证
)

:step6

:: ============================================================
:: Step 6: 安装 DataAnalysis-Agent
:: ============================================================
echo [6/8] 安装 DataAnalysis-Agent（LLM Agent）...
echo.

cd /d "!AGENT_DIR!"

:: 创建虚拟环境
if exist ".venv\Scripts\python.exe" (
    echo   虚拟环境已存在，跳过创建。
) else (
    if exist ".venv" (
        echo   旧的 .venv 目录存在但不完整，正在删除重建...
        rmdir /s /q ".venv"
    )
    "!PYTHON!" -m venv .venv
    if errorlevel 1 (
        echo   [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo   [完成] 虚拟环境已创建
)

:: 升级 pip
echo   升级 pip ...
.\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet 2>nul

:: 安装依赖
if not exist "requirements.txt" (
    echo   [错误] 未找到 requirements.txt
    pause
    exit /b 1
)

echo   安装 Python 依赖 ...
.\.venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 (
    echo   [错误] 依赖安装失败，请检查网络连接后重试
    pause
    exit /b 1
)
echo   [完成] DataAnalysis-Agent 安装完成
echo.

:: ============================================================
:: Step 7: 安装 Playwright Chromium
:: ============================================================
echo [7/8] 安装 Playwright 浏览器（约 180MB，请耐心等待）...
echo.

set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
.\.venv\Scripts\python.exe -m playwright install --force chromium
if errorlevel 1 (
    echo   [警告] Playwright 浏览器安装失败
    echo          如果不需要排片预测功能可以忽略此错误
    echo          否则请手动执行: .venv\Scripts\python.exe -m playwright install chromium
)
echo.

:: ============================================================
:: Step 8: 配置 .env
:: ============================================================
echo [8/8] 配置凭证文件...
echo.

cd /d "!AGENT_DIR!"

if not exist ".env" (
    echo   未找到 .env 文件，正在创建模板...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
    ) else (
        (
            echo # 飞书应用凭证
            echo FEISHU_APP_ID=cli_xxxxxxxxxxxx
            echo FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
            echo.
            echo # DeepSeek API
            echo DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
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
            echo.
            echo # 外部 Bot 路径（可选，默认自动识别本项目的同级目录）
            echo # REELCLEAN_DIR=D:\ReelClean-bot
            echo # PREDICTION_DIR=D:\Prediction-Bot
            echo # FEISHU_BOT_DIR=D:\feishu-bot
        ) > ".env"
    )
    echo.
    echo   ========================================
    echo    重要：需要手动配置 .env 文件！
    echo   ========================================
    echo.
    echo   请填写以下凭证（用记事本打开 .env）：
    echo.
    echo   1. FEISHU_APP_ID      — 飞书应用 App ID
    echo   2. FEISHU_APP_SECRET  — 飞书应用 App Secret
    echo   3. DEEPSEEK_API_KEY   — DeepSeek API Key
    echo.
    echo   是否现在打开 .env 文件编辑？[Y/N]
    set /p "OPEN_ENV="
    if /i "!OPEN_ENV!"=="Y" start notepad ".env"
    echo.
) else (
    echo   .env 文件已存在，跳过。
    echo.
)

:: ============================================================
:: 安装完成
:: ============================================================
echo ========================================
echo   全部安装完成！
echo ========================================
echo.
echo   已安装的项目：
echo     [Agent]  !AGENT_DIR!
if exist "!REELCLEAN_DIR!" echo     [Bot  ]  !REELCLEAN_DIR!
if exist "!PREDICTION_DIR!" echo     [Bot  ]  !PREDICTION_DIR!
if exist "!FEISHU_DIR!" echo     [Bot  ]  !FEISHU_DIR!
echo.
echo   启动方式:
echo     1. 双击 DataAnalysis-Agent 目录中的 start.vbs（推荐）
echo     2. 或运行: .venv\Scripts\python main.py
echo.
echo   使用流程:
echo     1. 确保 .env 已配置飞书和 DeepSeek 凭证
echo     2. 启动后在飞书群聊中 @机器人 发消息
echo     3. 自然语言描述需求，Agent 自动路由
echo.
echo   需要帮助？查看 README.md 了解详情
echo.

pause
exit /b 0

:: ============================================================
:: 子程序：为单个 Bot 创建 venv 并安装依赖
:: ============================================================
:install_bot_venv
set "BOT_NAME=%~1"
set "BOT_DIR=%~2"

echo   创建虚拟环境 ...

if exist "!BOT_DIR!\.venv\Scripts\python.exe" (
    echo   虚拟环境已存在，跳过创建。
) else (
    if exist "!BOT_DIR!\.venv" (
        rmdir /s /q "!BOT_DIR!\.venv"
    )
    "!PYTHON!" -m venv "!BOT_DIR!\.venv"
    if errorlevel 1 (
        echo   [错误] %BOT_NAME% 虚拟环境创建失败
        exit /b 1
    )
    echo   虚拟环境已创建
)

echo   安装依赖 ...
if not exist "!BOT_DIR!\requirements.txt" (
    echo   [警告] 未找到 requirements.txt，跳过依赖安装
    exit /b 0
)

"!BOT_DIR!\.venv\Scripts\pip.exe" install -r "!BOT_DIR!\requirements.txt"
if errorlevel 1 (
    echo   [错误] %BOT_NAME% 依赖安装失败
    exit /b 1
)
echo   依赖安装完成
exit /b 0
