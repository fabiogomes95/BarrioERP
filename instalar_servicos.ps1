# Instala o BarrioERP como serviço do Windows (backend + frontend), pra iniciar
# sozinho sempre que o PC ligar — sem precisar rodar nada manualmente.
#
# COMO USAR:
#   1. Abra o menu Iniciar, digite "PowerShell"
#   2. Clique com o botão direito em "Windows PowerShell" -> "Executar como administrador"
#   3. Cole e rode:  C:\Users\Fabinho\Documents\BarrioERP\instalar_servicos.ps1
#      (se der erro de "execution policy", rode antes:
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force)

$nssm = "C:\Users\Fabinho\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$root = "C:\Users\Fabinho\Documents\BarrioERP"

# ── Backend ──────────────────────────────────────────────────────────────────
& $nssm install BarrioERP-Backend "$root\backend\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
& $nssm set BarrioERP-Backend AppDirectory "$root\backend"
& $nssm set BarrioERP-Backend AppStdout "$root\backend\service_out.log"
& $nssm set BarrioERP-Backend AppStderr "$root\backend\service_err.log"
& $nssm set BarrioERP-Backend AppRotateFiles 1
& $nssm set BarrioERP-Backend Start SERVICE_AUTO_START
& $nssm set BarrioERP-Backend DependOnService postgresql-x64-16

# ── Frontend ─────────────────────────────────────────────────────────────────
& $nssm install BarrioERP-Frontend "C:\Program Files\nodejs\npm.cmd" "run dev"
& $nssm set BarrioERP-Frontend AppDirectory "$root\frontend"
& $nssm set BarrioERP-Frontend AppStdout "$root\frontend\service_out.log"
& $nssm set BarrioERP-Frontend AppStderr "$root\frontend\service_err.log"
& $nssm set BarrioERP-Frontend AppRotateFiles 1
& $nssm set BarrioERP-Frontend Start SERVICE_AUTO_START
& $nssm set BarrioERP-Frontend DependOnService BarrioERP-Backend

Write-Host ""
Write-Host "Servicos instalados! Eles vao iniciar sozinhos no proximo boot do Windows." -ForegroundColor Green
Write-Host ""
Write-Host "O sistema que voce ja tem rodando manualmente continua ativo por enquanto."
Write-Host "Pra colocar os servicos pra rodar AGORA (troca o processo manual pelo servico):"
Write-Host "  1. Feche o backend/frontend manual (ou deixe, os servicos vao tentar outra porta se ja estiver ocupada)"
Write-Host "  2. Start-Service BarrioERP-Backend"
Write-Host "  3. Start-Service BarrioERP-Frontend"
Write-Host ""
Write-Host "Pra checar status:   Get-Service BarrioERP-*"
Write-Host "Pra parar:           Stop-Service BarrioERP-Backend, BarrioERP-Frontend"
Write-Host "Pra desinstalar:     & '$nssm' remove BarrioERP-Backend confirm; & '$nssm' remove BarrioERP-Frontend confirm"
