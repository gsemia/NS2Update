if  not exist dist\ns2update.exe then goto error
 
cmd /c env.cmd


set h=%TIME:~0,2%
set m=%TIME:~3,2%
set s=%TIME:~6,2%
set t=%h%%m%%s%

if not exist %ns2updatedeploypath% goto error2

copy dist\ns2update.exe %ns2updatedeploypath%\ns2update%t%.exe
copy /y dist\ns2update.exe %ns2updatedeploypath%\ns2\ns2update.exe

goto end


:error1
echo please run build.cmd first
pause

goto end

:error2
echo Please create a env.cmd and add an existing path to the env variable "ns2updatedeploypath"
pause
goto end

:end

pause