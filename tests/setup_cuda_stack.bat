@echo off
REM Bootstrap CUDA 12.8 PyTorch and gsplat (main branch) for NullSplats.
REM Run this from an activated venv: call .venv\Scripts\activate.bat && call tests\setup_cuda_stack.bat

setlocal

REM Prefer CUDA 12.8 toolchain for builds.
set "CUDA_HOME=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8"
set "CUDA_PATH=%CUDA_HOME%"
set "PATH=%CUDA_HOME%\bin;%CUDA_HOME%\lib\x64;%PATH%"

echo Updating pip...
python -m pip install --upgrade pip

echo Uninstalling any existing torch/gsplat to avoid ABI mismatches...
python -m pip uninstall -y torch torchvision torchaudio gsplat

echo Installing torch/cu12.8 from the official PyTorch index...
python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

echo Installing gsplat from main (builds against the already-installed torch)...
REM Disable build isolation so torch is visible during the extension build.
set PIP_NO_BUILD_ISOLATION=1
python -m pip install --no-deps --no-build-isolation git+https://github.com/nerfstudio-project/gsplat.git@main
set PIP_NO_BUILD_ISOLATION=

echo CUDA stack install complete.
endlocal
