del dist\console.exe 
del dist\ns2update.exe
rmdir /s /q build
call env.cmd

%python27_64% pyinstaller-1.5.1/Build.py console.spec

move dist\console.exe dist\ns2update.exe

