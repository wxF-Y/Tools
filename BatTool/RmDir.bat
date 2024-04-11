set rootPath=C:\Users\wxF\AppData\Roaming\

set regList=adbk_pp chat_pp common_pp dzip_pp jdesk_pp mark_pp search_pp tabx_pp ultra_pp write_pp

for %%i in (%regList%) do (
    rd /S /Q %rootPath%%%i
)
