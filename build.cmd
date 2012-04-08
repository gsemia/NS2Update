del dist\console.exe 
del dist\ns2update.exe
rmdir /s /q build

rem #/c/Python27/python pyinstaller-1.5.1/Makespec.py src/console.py --onefile
python pyinstaller-1.5.1/Build.py console.spec

move dist\console.exe dist\ns2update.exe

