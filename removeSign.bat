for /r %%i in (*) do (  
start "" "RemoveCertificate.exe" --file=%%i)
pause