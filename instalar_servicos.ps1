# Instala o BarrioERP como serviço do Windows, pra iniciar sozinho sempre que
# o PC ligar — sem precisar rodar nada manualmente.
#
# O backend serve a API e o frontend (build de produção em frontend/dist/)
# juntos, em dois listeners: HTTP puro na rede local (fallback sem depender do
# Tailscale) e HTTPS via certificado do Tailscale (necessário pra Web Share API
# e pra acesso remoto confiável).
#
# COMO USAR:
#   1. Abra o menu Iniciar, digite "PowerShell"
#   2. Clique com o botão direito em "Windows PowerShell" -> "Executar como administrador"
#   3. Cole e rode:  D:\Users\Fabinho\Documents\BarrioERP\instalar_servicos.ps1
#      (se der erro de "execution policy", rode antes:
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force)
#
# Pré-requisito pro serviço HTTPS: certificado já emitido em
# backend\certs\ (ver backend\certs\renovar-cert.ps1).

$nssm = "C:\Users\Fabinho\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$root = "D:\Users\Fabinho\Documents\BarrioERP"
$certName = "gomes-pc.cod-aldebaran.ts.net"

# ── Backend HTTP (rede local, fallback sem Tailscale) ───────────────────────
& $nssm install BarrioERP-Backend "$root\backend\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
& $nssm set BarrioERP-Backend AppDirectory "$root\backend"
& $nssm set BarrioERP-Backend AppStdout "$root\backend\service_out.log"
& $nssm set BarrioERP-Backend AppStderr "$root\backend\service_err.log"
& $nssm set BarrioERP-Backend AppRotateFiles 1
& $nssm set BarrioERP-Backend Start SERVICE_AUTO_START
& $nssm set BarrioERP-Backend DependOnService postgresql-x64-16

# ── Backend HTTPS (via certificado Tailscale, porta 443) ────────────────────
& $nssm install BarrioERP-Backend-TLS "$root\backend\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 443 --ssl-certfile `"$root\backend\certs\$certName.crt`" --ssl-keyfile `"$root\backend\certs\$certName.key`""
& $nssm set BarrioERP-Backend-TLS AppDirectory "$root\backend"
& $nssm set BarrioERP-Backend-TLS AppStdout "$root\backend\service_tls_out.log"
& $nssm set BarrioERP-Backend-TLS AppStderr "$root\backend\service_tls_err.log"
& $nssm set BarrioERP-Backend-TLS AppRotateFiles 1
& $nssm set BarrioERP-Backend-TLS Start SERVICE_AUTO_START
& $nssm set BarrioERP-Backend-TLS DependOnService postgresql-x64-16

Write-Host ""
Write-Host "Servicos instalados! Eles vao iniciar sozinhos no proximo boot do Windows." -ForegroundColor Green
Write-Host ""
Write-Host "Pra colocar os servicos pra rodar AGORA:"
Write-Host "  Start-Service BarrioERP-Backend"
Write-Host "  Start-Service BarrioERP-Backend-TLS"
Write-Host ""
Write-Host "Pra checar status:   Get-Service BarrioERP-*"
Write-Host "Pra parar:           Stop-Service BarrioERP-Backend, BarrioERP-Backend-TLS"
Write-Host "Pra desinstalar:     & '$nssm' remove BarrioERP-Backend confirm; & '$nssm' remove BarrioERP-Backend-TLS confirm"
