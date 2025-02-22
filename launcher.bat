@echo off
setlocal

:: Define working directory in Downloads
set "workspace=%USERPROFILE%\Downloads\character.py"

:: URLs for pychai.py and launcher.bat
set "pychai_url=https://raw.githubusercontent.com/cdexstra1/character.py/main/pychai.py"
set "python_installer_url=https://www.python.org/ftp/python/3.10.4/python-3.10.4-amd64.exe"
set "python_installer=%USERPROFILE%\Downloads\python_installer.exe"

:: Check if Python is installed
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed. Installing Python...
    call :install_python
)

:: Create workspace folder if it doesn't exist
if not exist "%workspace%" (
    mkdir "%workspace%"
)

:: Download pychai.py
call :download_file %pychai_url% "%workspace%\pychai.py"

:: Run pychai.py using the installed Python
echo Running pychai.py...
python "%workspace%\pychai.py"
goto :eof

:: Install Python function
:install_python
echo Downloading Python installer...
curl -L -o "%python_installer%" %python_installer_url%

echo Installing Python...
start /wait %python_installer% /quiet InstallAllUsers=1 PrependPath=1

echo Python installed successfully. Cleaning up...
del "%python_installer%"
goto :eof

:: Download file function
:download_file
set "url=%1"
set "path=%2"
echo Downloading %url%...
curl -L -o "%path%" %url%
goto :eof
