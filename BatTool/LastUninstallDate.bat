set rootReg=HKLM\SOFTWARE\
set UninstallDate="2024-01-11 10:18:35"

set regList=Anything BiscuitZip JianDesk ADBlockMaster LevinBoot SmartChat SmartWriter SuperBookmark TabXExplorer "Ultra Uninstaller"

for %%i in (%regList%) do (
    reg delete "%rootReg%%%~i" /v LastUninstallDate /f /reg:32
    reg add "%rootReg%%%~i" /v LastUninstallDate /t REG_SZ /d %UninstallDate% /f /reg:32
)

pause
