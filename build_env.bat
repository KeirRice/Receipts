:: Create a virtual environment for the receipts.
::
@ECHO OFF
where mkvirtualenv >nul 2>&1
IF %errorlevel% neq 0 (ECHO You need to install virtualenv. http://timmyreilly.azurewebsites.net/python-pip-virtualenv-installation-on-windows/ & GOTO:END)

set "venvwrapper.default_workon_home=%USERPROFILE%\Envs"
if not defined WORKON_HOME  set "WORKON_HOME=%venvwrapper.default_workon_home%"
set "venvwrapper.workon_home=%WORKON_HOME%"

if not exist "%WORKON_HOME%\receipts" (
	ECHO receipts virtual env not found. Creating it.

	ECHO ^>mkvirtualenv receipts
	call mkvirtualenv receipts
	ECHO ^>workon receipts
	call workon receipts
	ECHO ^>setprojectdir .
	call setprojectdir .
) ELSE (
	ECHO receipts virtual env found.
	ECHO ^>workon receipts
	call workon receipts
)

ECHO ^>pip install -r requirements.txt
pip install -r requirements.txt


:END
:pauseIfDoubleClicked
SETLOCAL enabledelayedexpansion
SET testl=%cmdcmdline:"=%
SET testr=!testl:%~nx0=!
IF NOT "%testl%" == "%testr%" PAUSE
GOTO :eof

:eof
EXIT /b %errorlevel%