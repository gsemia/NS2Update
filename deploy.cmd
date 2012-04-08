if  not exist dist\ns2update.exe then goto error
 
set h=%TIME:~0,2%
set m=%TIME:~3,2%
set s=%TIME:~6,2%
set t=%h%%m%%s%

copy dist\ns2update.exe \\escher\d$\server\ns2\ns2update%t%.exe
copy /y dist\ns2update.exe \\escher\d$\server\ns2\ns2update.exe

goto end


:error
echo please run build.cmd first
pause

goto end


:end

pause