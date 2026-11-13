@echo off
setlocal
set "STUDIO_ROOT=%~dp0.."
set "PATH=%USERPROFILE%\.cargo\bin;%STUDIO_ROOT%\wasm-bindgen-0.2.129-x86_64-pc-windows-msvc;%STUDIO_ROOT%\tools;%PATH%"
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 >nul
if errorlevel 1 exit /b %ERRORLEVEL%
cd /d "%STUDIO_ROOT%\packages\vitryne-web"
call "%STUDIO_ROOT%\tools\pnpm.cmd" run wasm
if errorlevel 1 exit /b %ERRORLEVEL%
cd /d "%STUDIO_ROOT%"
cargo build --release -p vitryne-cli --manifest-path packages\vitryne-engine\Cargo.toml
if errorlevel 1 exit /b %ERRORLEVEL%
packages\vitryne-engine\target\release\vitryne.exe export-app-assets packages\vitryne-web\public
if errorlevel 1 exit /b %ERRORLEVEL%
packages\vitryne-engine\target\release\vitryne.exe export-bench-assets packages\vitryne-web\public\bench-assets
if errorlevel 1 exit /b %ERRORLEVEL%
cd /d "%STUDIO_ROOT%\packages\vitryne-web"
call "%STUDIO_ROOT%\tools\pnpm.cmd" exec tsc -b
if errorlevel 1 exit /b %ERRORLEVEL%
call "%STUDIO_ROOT%\tools\pnpm.cmd" exec vite build
exit /b %ERRORLEVEL%
