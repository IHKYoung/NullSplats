@echo off
setlocal EnableDelayedExpansion
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"
if exist "%APP_DIR%\NullSplats-portable" set "APP_DIR=%APP_DIR%\NullSplats-portable"

rem Prefer bundled base Python; fall back to venv python.
set "PY_HOME=%APP_DIR%\python"
set "PYTHON_EXE=%PY_HOME%\python.exe"
if not exist "%PYTHON_EXE%" (
  set "PY_HOME="
  set "PYTHON_EXE=%APP_DIR%\venv\Scripts\python.exe"
)
if not exist "%PYTHON_EXE%" (
  echo [error] Bundled python not found at %APP_DIR%\python or %APP_DIR%\venv
  pause
  exit /b 1
)

set "VIRTUAL_ENV=%APP_DIR%\venv"
set "PYTHONPATH=%APP_DIR%\venv\Lib\site-packages;%PYTHONPATH%"
set "PATH=%APP_DIR%\venv\Scripts;%APP_DIR%\venv\Lib\site-packages\torch\lib;%PATH%"
set "PYTHONNOUSERSITE=1"
if exist "%APP_DIR%\cuda\bin" set "PATH=%APP_DIR%\cuda\bin;%PATH%"
if exist "%APP_DIR%\cuda\lib\x64" set "PATH=%APP_DIR%\cuda\lib\x64;%PATH%"
set "CUDA_HOME=%APP_DIR%\cuda"
set "CUDA_PATH=%APP_DIR%\cuda"
set "TORCH_EXTENSIONS_DIR=%APP_DIR%\torch_extensions"
if not exist "%TORCH_EXTENSIONS_DIR%" mkdir "%TORCH_EXTENSIONS_DIR%" >nul 2>&1
set "COLMAP_ROOT=%APP_DIR%\tools\colmap"
if exist "%COLMAP_ROOT%\bin" set "PATH=%COLMAP_ROOT%\bin;%PATH%"
if exist "%COLMAP_ROOT%\lib" set "PATH=%COLMAP_ROOT%\lib;%PATH%"
if defined PY_HOME set "PYTHONHOME=%PY_HOME%"

pushd "%APP_DIR%" >nul
if /I "%1"=="--test" (
  shift
  call set "TEST_ARGS=%%*"
  if exist "%APP_DIR%\test.py" (
    "%PYTHON_EXE%" "%APP_DIR%\test.py" !TEST_ARGS!
  ) else if exist "%APP_DIR%\..\test.py" (
    "%PYTHON_EXE%" -c "import runpy, sys; sys.path.insert(0, r'%APP_DIR%'); runpy.run_path(r'%APP_DIR%\..\test.py', run_name='__main__')" !TEST_ARGS!
  ) else (
    echo [error] test.py not found at %APP_DIR% or %APP_DIR%\..
    popd >nul
    exit /b 1
  )
  popd >nul
  exit /b %ERRORLEVEL%
)
"%PYTHON_EXE%" "%APP_DIR%\main.py" %*
popd >nul
