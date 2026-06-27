$python = "C:\Users\Fabinho\Documents\BarrioERP\backend\.venv\Scripts\python.exe"
$backend = "C:\Users\Fabinho\Documents\BarrioERP\backend"

# Aguarda o banco (serviço Windows, já inicia com o PC)
$tries = 0
do {
    Start-Sleep -Seconds 1
    $tries++
    $ok = (& "$backend\.venv\Scripts\python.exe" -c "import psycopg2; psycopg2.connect('host=localhost port=5432 dbname=barrio user=barrio password=barrio_dev'); print('ok')" 2>&1) -eq 'ok'
} while (-not $ok -and $tries -lt 15)

# Inicia o backend (invisível)
$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = $python
$pinfo.Arguments = "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
$pinfo.WorkingDirectory = $backend
$pinfo.UseShellExecute = $false
$pinfo.CreateNoWindow = $true
[System.Diagnostics.Process]::Start($pinfo) | Out-Null

# Aguarda o backend subir
Start-Sleep -Seconds 4

# Abre o navegador
Start-Process "http://localhost:8000"
