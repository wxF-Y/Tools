<#
.SYNOPSIS
  将指定目录下所有 .h 和 .cpp 文件转换为 UTF-8 with BOM 编码
.DESCRIPTION
  此脚本会递归扫描指定目录，将所有 C/C++ 头文件和源文件转换为带 BOM 的 UTF-8 编码
.PARAMETER ProjectPath
  要处理的根目录路径
.EXAMPLE
  .\ConvertToUTF8BOM.ps1 -ProjectPath "C:\MyProject"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectPath
)

# 检查路径是否存在
if (-not (Test-Path -Path $ProjectPath)) {
    Write-Error "指定的路径不存在: $ProjectPath"
    exit 1
}

# 获取所有 .h 和 .cpp 文件
$files = Get-ChildItem -Path $ProjectPath -Recurse -Include "*.h", "*.cpp", "*.vcxproj", "*.sln", "*.vcxproj.filters"

if ($files.Count -eq 0) {
    Write-Host "未找到任何 .h 或 .cpp 文件"
    exit
}

# 处理每个文件
$count = 0
foreach ($file in $files) {
    try {
        # 读取文件内容
        $content = Get-Content $file.FullName -Raw
        
        # 以 UTF-8 with BOM 编码重新写入文件
        [IO.File]::WriteAllText($file.FullName, $content, [Text.Encoding]::UTF8)
        
        $count++
        Write-Host "已转换: $($file.FullName)"
    }
    catch {
        Write-Warning "处理文件失败: $($file.FullName)"
        Write-Warning $_.Exception.Message
    }
}

Write-Host "`n转换完成! 共处理了 $count 个文件。"