param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "RomPatcher" `
    --icon "assets\\rompatcher.ico" `
    --paths "src" `
    "app.py"
