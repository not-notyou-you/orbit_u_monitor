# run.ps1 — jalankan API + web UI Orbit-U: The Monitor di mesin ini.
#
# Lingkungan sudah disiapkan: venv/ (Python 3.10.11) dan PostgreSQL 14 lokal
# (database themonitor, PostGIS 3.4, schema + migrasi 001-026 terpasang).
# TimescaleDB tidak terpasang — schema.sql sudah menanganinya sebagai opsional.
#
# Pakai:  .\run.ps1          -> http://localhost:8001
#         .\run.ps1 -Reload  -> auto-reload saat kode berubah (dev)

param([switch]$Reload)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    throw "venv tidak ada. Buat dulu: & `"$env:LOCALAPPDATA\Programs\Python\Python310\python.exe`" -m venv venv; .\venv\Scripts\python.exe -m pip install -r requirements.txt"
}

# Cek PostgreSQL hidup sebelum uvicorn, supaya gagalnya jelas.
if ((Get-Service postgresql-x64-14 -ErrorAction SilentlyContinue).Status -ne "Running") {
    Write-Warning "Service postgresql-x64-14 tidak berjalan. Jalankan: Start-Service postgresql-x64-14"
}

$args = @("-m","uvicorn","api.main:app","--host","0.0.0.0","--port","8001")
if ($Reload) { $args += "--reload" }

Write-Host "Landing : http://localhost:8001"      -ForegroundColor Cyan
Write-Host "Aplikasi: http://localhost:8001/app"  -ForegroundColor Cyan
Write-Host "API docs: http://localhost:8001/docs" -ForegroundColor Cyan

& ".\venv\Scripts\python.exe" @args
