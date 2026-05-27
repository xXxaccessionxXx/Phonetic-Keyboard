@echo off
echo Building Phonetic Keyboard...

:: Activate the virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo Activated virtual environment.
) else (
    echo WARNING: Virtual environment not found. Using global Python environment...
)

:: Build the executable using the existing PyInstaller spec file
echo Running PyInstaller...
pyinstaller PhoneticKeyboard.spec --clean

echo.
echo =======================================================
echo Build complete! Your executable is in the "dist" folder.
echo =======================================================
echo.
echo NOTE ON ANTIVIRUS (McAfee):
echo It is very common for McAfee and Windows Defender to flag
echo executables created by PyInstaller as viruses. This is a
echo FALSE POSITIVE caused by how PyInstaller bundles Python.
echo.
echo To run your app, please open McAfee settings and add an
echo exception/exclusion for the "dist" folder or the .exe file.
echo.
pause
