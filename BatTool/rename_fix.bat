rem 在 set "newfilename=!filename:被替换值=替换值!" 中
rem 直接填写
rem 使用变量再替换 有空格时替换不成功
@echo off
setlocal enabledelayedexpansion
chcp 65001
 
for %%f in (*%search%*) do (
    set "filename=%%~nf"
    set "newfilename=!filename:被替换值=替换值!"
    ren "%%f" "!newfilename!%%~xf"
)
 
echo done