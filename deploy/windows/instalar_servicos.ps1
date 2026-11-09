# Instala o BarrioERP como serviço do Windows, pra iniciar sozinho sempre que
# o PC ligar — sem precisar rodar nada manualmente.
#
# O backend serve a API e o frontend (build de produção em frontend/dist/)
# juntos, em HTTP puro na porta 8000. O HTTPS (necessário pra Web Share API e
# pra acesso remoto confiável) fica por conta do `tailscale serve`, que faz o
# proxy da 443 pra 8000 e renova o certificado sozinho:
#   tailscale serve --bg http://127.0.0.1:8000
# (a config persiste entre reboots; ver com `tailscale serve status`).
# A porta 8000 continua aberta na rede local como fallback sem Tailscale.
#
# COMO USAR:
#   1. Abra o menu Iniciar, digite "PowerShell"
#   2. Clique com o botão direito em "Windows PowerShell" -> "Executar como administrador"
#   3. Cole e rode:  D:\Users\Fabinho\Documents\BarrioERP\deploy\windows\instalar_servicos.ps1
#      (se der erro de "execution policy", rode antes:
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force)

$nssm = "C:\Users\Fabinho\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path   # raiz do repositório
New-Item -ItemType Directory -Force "$root\logs" | Out-Null

# ── Backend HTTP (rede local, fallback sem Tailscale) ───────────────────────
& $nssm install BarrioERP-Backend "$root\backend\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
& $nssm set BarrioERP-Backend AppDirectory "$root\backend"
& $nssm set BarrioERP-Backend AppStdout "$root\logs\service_out.log"
& $nssm set BarrioERP-Backend AppStderr "$root\logs\service_err.log"
& $nssm set BarrioERP-Backend AppRotateFiles 1
& $nssm set BarrioERP-Backend Start SERVICE_AUTO_START
& $nssm set BarrioERP-Backend DependOnService postgresql-x64-16

# ── HTTPS via Tailscale Serve (certificado renovado automaticamente) ────────
tailscale serve --bg http://127.0.0.1:8000

Write-Host ""
Write-Host "Servicos instalados! Eles vao iniciar sozinhos no proximo boot do Windows." -ForegroundColor Green
Write-Host ""
Write-Host "Pra colocar os servicos pra rodar AGORA:"
Write-Host "  Start-Service BarrioERP-Backend"

Write-Host ""
Write-Host "Pra checar status:   Get-Service BarrioERP-*"
Write-Host "Pra parar:           Stop-Service BarrioERP-Backend"
Write-Host "Pra desinstalar:     & '$nssm' remove BarrioERP-Backend confirm"
