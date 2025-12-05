@echo off
setlocal
rem Run gsplat simple_trainer against a cached scene without the viewer.
rem No arguments needed; edit the SCENE or step settings below if required.

set SCENE=20251121_120658_720
set MAX_STEPS=3000
set STEPS_SCALER=0.25

set DATA_DIR=cache\outputs\%SCENE%\sfm
set RESULT_DIR=cache\outputs\%SCENE%\simple_trainer

echo Running simple_trainer on scene %SCENE% with data dir %DATA_DIR%
python tools\gsplat_examples\simple_trainer.py default --disable-viewer --data-dir "%DATA_DIR%" --result-dir "%RESULT_DIR%" --max-steps %MAX_STEPS% --steps-scaler %STEPS_SCALER% --save-ply --render-traj-path interp
