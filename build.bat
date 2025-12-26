@echo on
setlocal EnableExtensions EnableDelayedExpansion

rem Simple portable bundle packer. Copies app, venv, tools, and CUDA runtime into ./build/NullSplats-portable.

rem --- Paths and defaults ---
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\.venv"
set "BUILD_DIR=%ROOT%\build"
set "OUT_DIR=%BUILD_DIR%\NullSplats-portable"
set "ZIP_PATH=%BUILD_DIR%\NullSplats-portable.zip"
set "COLMAP_SRC=%ROOT%\tools\colmap"
set "SHARP_SRC=%ROOT%\tools\sharp"
set "CUDA_SRC=%CUDA_SRC%"
if "%CUDA_SRC%"=="" set "CUDA_SRC=%CUDA_PATH%"
if "%CUDA_SRC%"=="" set "CUDA_SRC=%CUDA_HOME%"
if "%CUDA_SRC%"=="" set "CUDA_SRC=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8"
set "PY_BASE_SRC=C:\Program Files\Python310"
set "TORCH_EXT_SRC=%LOCALAPPDATA%\torch_extensions"
set "TORCH_EXT_DEST=%OUT_DIR%\torch_extensions"
if "%SKIP_CLEAN%"=="" set "SKIP_CLEAN=0"
if "%SKIP_ZIP%"=="" set "SKIP_ZIP=0"
if "%REQUIRE_CUDA%"=="" set "REQUIRE_CUDA=1"
if "%COPY_TORCH_EXT%"=="" set "COPY_TORCH_EXT=0"
if "%SCRUB_PERSONAL%"=="" set "SCRUB_PERSONAL=1"
if "%SKIP_VENV_SETUP%"=="" set "SKIP_VENV_SETUP=1"
if "%REBUILD_GSPLAT%"=="" set "REBUILD_GSPLAT=1"
if "%GSPLAT_VERSION%"=="" set "GSPLAT_VERSION=1.5.3"
if "%GSPLAT_ARCH_LIST%"=="" set "GSPLAT_ARCH_LIST=8.6;8.9+PTX"
if "%PIP_CACHE_DIR%"=="" set "PIP_CACHE_DIR=%LOCALAPPDATA%\pip\Cache"

echo.
echo === NullSplats portable bundle ===
echo Repo root:   %ROOT%
echo Venv:        %VENV%
echo Output:      %OUT_DIR%
echo COLMAP src:  %COLMAP_SRC%
echo SHARP src:   %SHARP_SRC%
echo CUDA src:    %CUDA_SRC%
echo Python base: %PY_BASE_SRC%
echo Torch ext src: %TORCH_EXT_SRC%
echo Pip cache dir: %PIP_CACHE_DIR%
echo Rebuild gsplat: %REBUILD_GSPLAT% (archs=%GSPLAT_ARCH_LIST% version=%GSPLAT_VERSION%)
echo Skip clean:  %SKIP_CLEAN%
echo Skip zip:    %SKIP_ZIP%
echo Require CUDA copy: %REQUIRE_CUDA%
echo Copy torch ext cache: %COPY_TORCH_EXT%
echo Scrub personal data: %SCRUB_PERSONAL%
echo Skip venv setup: %SKIP_VENV_SETUP%
echo.


if "%SKIP_VENV_SETUP%"=="0" goto VENV_SETUP
echo Skipping venv setup (torch/gsplat install).

if "%SKIP_CLEAN%"=="0" (
    echo Cleaning build folder...
    if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%"
)
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%" >nul 2>&1
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%" >nul 2>&1
if "%SKIP_CLEAN%"=="0" if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>&1

echo Copying package...
robocopy "%ROOT%\nullsplats" "%OUT_DIR%\nullsplats" /mir >nul
copy /y "%ROOT%\main.py" "%OUT_DIR%\" >nul
if exist "%ROOT%\test.py" copy /y "%ROOT%\test.py" "%OUT_DIR%\" >nul
if exist "%ROOT%\assets" robocopy "%ROOT%\assets" "%OUT_DIR%\assets" /mir >nul
robocopy "%ROOT%\nullsplats\ui\shaders" "%OUT_DIR%\nullsplats\ui\shaders" /mir >nul
if exist "%COLMAP_SRC%" robocopy "%COLMAP_SRC%" "%OUT_DIR%\tools\colmap" /mir >nul
if exist "%SHARP_SRC%" robocopy "%SHARP_SRC%" "%OUT_DIR%\tools\sharp" /mir >nul

echo Copying venv...
robocopy "%VENV%" "%OUT_DIR%\venv" /mir >nul

echo Copying base Python runtime...
robocopy "%PY_BASE_SRC%" "%OUT_DIR%\python" /mir >nul

echo Ensuring torch extensions cache...
if not exist "%TORCH_EXT_DEST%" mkdir "%TORCH_EXT_DEST%" >nul 2>&1
if "%COPY_TORCH_EXT%"=="1" if exist "%TORCH_EXT_SRC%" robocopy "%TORCH_EXT_SRC%" "%TORCH_EXT_DEST%" /mir >nul

echo Pruning unused Python packages...
for %%D in ("%OUT_DIR%\venv\Lib\site-packages\tyro" "%OUT_DIR%\venv\Lib\site-packages\tyro-*.dist-info") do (
    if exist "%%~D" rd /s /q "%%~D"
)
for /r "%OUT_DIR%\venv" %%F in (*.pdb *.lib *.exp) do del /f /q "%%F" >nul 2>&1

rem Copy CUDA runtime DLLs if available.
if exist "%CUDA_SRC%" (
    echo Copying CUDA runtime from %CUDA_SRC% ...
    set "CUDA_DEST_BIN=%OUT_DIR%\cuda\bin"
    set "CUDA_DEST_LIB=%OUT_DIR%\cuda\lib\x64"
    mkdir "%OUT_DIR%\cuda" >nul 2>&1
    mkdir "!CUDA_DEST_BIN!" >nul 2>&1
    mkdir "!CUDA_DEST_LIB!" >nul 2>&1
    for %%P in (cudart64_*.dll cublas64_*.dll cublasLt64_*.dll cusparse64_*.dll cusolver64_*.dll cufft64_*.dll curand64_*.dll cudnn64_*.dll nvrtc64_*.dll nvrtc-builtins64_*.dll nvJitLink_*.dll) do (
        if exist "%CUDA_SRC%\bin\%%P" copy /y "%CUDA_SRC%\bin\%%P" "!CUDA_DEST_BIN!\" >nul
        if exist "%CUDA_SRC%\lib\x64\%%P" copy /y "%CUDA_SRC%\lib\x64\%%P" "!CUDA_DEST_LIB!\" >nul
    )
) else (
    if "%REQUIRE_CUDA%"=="1" (
        echo [error] CUDA source not found at %CUDA_SRC% & exit /b 1
    ) else (
        echo [warn] CUDA source not found; skipping CUDA DLL copy.
    )
)

echo Writing run.bat launcher...
copy /y "%ROOT%\run.bat" "%OUT_DIR%\run.bat" >nul
copy /y "%ROOT%\run.bat" "%BUILD_DIR%\run-portable.bat" >nul 2>&1

if "%SCRUB_PERSONAL%"=="1" (
    echo Scrubbing personal data from bundle...
    if exist "%OUT_DIR%\cache" rd /s /q "%OUT_DIR%\cache"
    if exist "%OUT_DIR%\log" rd /s /q "%OUT_DIR%\log"
    if exist "%OUT_DIR%\torch_extensions" rd /s /q "%OUT_DIR%\torch_extensions"
)

if "%SKIP_ZIP%"=="0" (
    echo Creating zip archive...
    if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>&1
    if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>&1
    where 7z >nul 2>&1
    if %ERRORLEVEL%==0 (
        7z a -tzip -mx=0 "%ZIP_PATH%" "%OUT_DIR%\*" >nul
    ) else (
        echo [error] 7z not found in PATH; install 7-Zip CLI or add it to PATH. & exit /b 1
    )
)

echo.
echo [done] Portable bundle ready at %OUT_DIR%
if "%SKIP_ZIP%"=="0" echo [done] Zip archive created at %ZIP_PATH%
echo Use run.bat (in the bundle) or build\run-portable.bat to launch.
echo Build folder contents:
dir "%BUILD_DIR%" /b
exit /b 0

:VENV_SETUP
call "%VENV%\Scripts\pip.exe" install --cache-dir "%PIP_CACHE_DIR%" --force-reinstall --extra-index-url https://download.pytorch.org/whl/cu128 "torch==2.9.1+cu128" || exit /b 1
call "%VENV%\Scripts\python.exe" -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" || exit /b 1
set "CUDA_HOME=%CUDA_SRC%"
set "TORCH_CUDA_ARCH_LIST=%GSPLAT_ARCH_LIST%"
call "%VENV%\Scripts\pip.exe" install --cache-dir "%PIP_CACHE_DIR%" --no-deps --no-build-isolation --force-reinstall --no-binary=gsplat "gsplat==%GSPLAT_VERSION%" || exit /b 1
set "TORCH_CUDA_ARCH_LIST="
exit /b 0
