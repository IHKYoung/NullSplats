@echo off
setlocal
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

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
"%PYTHON_EXE%" "%APP_DIR%\main.py" %*
popd >nul
