@echo off
setlocal enabledelayedexpansion
chcp 65001

rem 参数检查
if "%~3"=="" (
    echo 用法: %~nx0 [目录] [被替换值] [替换值]
    echo 示例: %~nx0 "C:\MyFiles" "旧文本" "新文本"
    pause
    exit /b
)

set "search_dir=%~1"
set "old_str=%~2"
set "new_str=%~3"

if not defined search_dir set "search_dir=."

if not exist "%search_dir%\" (
    echo 目录不存在: "%search_dir%"
    exit /b
)

echo 正在处理目录: "%search_dir%"
echo 替换规则: "%old_str%" -> "%new_str%"

for /r "%search_dir%" %%f in (*) do (
    set "fullname=%%~nxf"
    set "newfullname=!fullname:%old_str%=%new_str%!"
    
    if not "!fullname!"=="!newfullname!" (
        echo 正在重命名: "%%~nxf" → "!newfullname!"
        ren "%%f" "!newfullname!"
    )
)

echo 完成!