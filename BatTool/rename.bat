@echo off
setlocal enabledelayedexpansion
chcp 65001
 
set "search=Ultra"
set "replace=WinOpt"
 
for %%f in (*%search%*) do (
    set "filename=%%~nf"
    set "newfilename=!filename:%search%=%replace%!"
    ren "%%f" "!newfilename!%%~xf"
)
 
echo done