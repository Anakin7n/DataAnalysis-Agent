@echo off
cd /d "%~dp0"

:: 找 Windows Terminal
set WT=
where wt >nul 2>nul && set WT=1

:: 找 pwsh (PS7)，没有则用 powershell
set PSHELL=powershell
where pwsh >nul 2>nul && set PSHELL=pwsh

if defined WT (
    start "" /min wt --title DataAnalysis-Agent %PSHELL% -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%~dp0'; & '%~dp0start.ps1'"
) else (
    start "" /min %PSHELL% -NoExit -ExecutionPolicy Bypass -File "%~dp0start.ps1"
)
