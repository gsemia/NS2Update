del dist\console.exe 
del dist-x86\ns2update.exe
rmdir /s /q build

rem #/c/Python27/python pyinstaller-1.5.1/Makespec.py src/console.py --onefile
f:\tools\python27_x86\python pyinstaller-1.5.1_x86/Build.py console.spec

move dist\console.exe dist-x86\ns2update.exe

