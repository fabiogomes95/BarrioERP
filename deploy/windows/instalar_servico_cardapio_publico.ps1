# Instala o "Cardápio Público" (app.public_menu) como serviço do Windows,
# separado do BarrioERP-Backend / BarrioERP-Backend-TLS.
#
# POR QUE UM SERVIÇO SEPARADO?
#   O ERP inteiro (login, comandas, caixa, admin) roda em BarrioERP-Backend* e
#   é feito pra ficar só na rede local/Tailscale (ver ARCHITECTURE.md). Este
#   serviço aqui é uma fatia pequena e isolada — só lê o cardápio e mostra
#   pra cliente — pensada pra, no futuro, ser exposta na internet via
#   `tailscale funnel` SEM abrir o resto do sistema junto.
#
#   Se algo der errado nele, o estrago é "alguém viu o cardápio". Ele nem
#   importa o código de autenticação/pedidos/caixa — não tem como.
#
# COMO USAR:
#   1. Abra o menu Iniciar, digite "PowerShell"
#   2. Clique com o botão direito em "Windows PowerShell" -> "Executar como administrador"
#   3. Cole e rode:  D:\Users\Fabinho\Documents\BarrioERP\deploy\windows\instalar_servico_cardapio_publico.ps1
#
# Antes de expor pra internet, configure no backend\.env:
#   PUBLIC_MENU_WHATSAPP=55DDDNUMERO   (número que recebe os pedidos)
#   PUBLIC_MENU_DISPLAY_NAME=Nome Fantasia do Bar

$nssm = "C:\Users\Fabinho\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path   # raiz do repositório
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$port = 8090

& $nssm install BarrioERP-Menu-Publico "$root\backend\.venv\Scripts\python.exe" "-m uvicorn app.public_menu:app --host 0.0.0.0 --port $port"
& $nssm set BarrioERP-Menu-Publico AppDirectory "$root\backend"
& $nssm set BarrioERP-Menu-Publico AppStdout "$root\logs\service_menu_out.log"
& $nssm set BarrioERP-Menu-Publico AppStderr "$root\logs\service_menu_err.log"
& $nssm set BarrioERP-Menu-Publico AppRotateFiles 1
& $nssm set BarrioERP-Menu-Publico Start SERVICE_AUTO_START
& $nssm set BarrioERP-Menu-Publico DependOnService postgresql-x64-16

Write-Host ""
Write-Host "Servico instalado! Vai iniciar sozinho no proximo boot do Windows." -ForegroundColor Green
Write-Host ""
Write-Host "Pra colocar pra rodar AGORA:"
Write-Host "  Start-Service BarrioERP-Menu-Publico"
Write-Host ""
Write-Host "Pra testar na rede local/Tailscale (sem expor pra internet ainda):"
Write-Host "  http://localhost:$port/cardapio/matriz"
Write-Host "  http://gomes-pc.cod-aldebaran.ts.net:$port/cardapio/matriz   (de outro dispositivo no seu Tailscale)"
Write-Host ""
Write-Host "Pra checar status:   Get-Service BarrioERP-Menu-Publico"
Write-Host "Pra parar:           Stop-Service BarrioERP-Menu-Publico"
Write-Host "Pra desinstalar:     & '$nssm' remove BarrioERP-Menu-Publico confirm"
Write-Host ""
Write-Host "Pra expor pro CLIENTE de verdade (fora do Tailscale), com o PC ligado:" -ForegroundColor Yellow
Write-Host "  tailscale funnel --bg --https=8443 http://127.0.0.1:$port"
Write-Host "  (o link publico vira https://gomes-pc.cod-aldebaran.ts.net:8443/cardapio/matriz )"
Write-Host "  NUNCA rode funnel na 443: ela e do ERP via tailscale serve (so tailnet)" -ForegroundColor Red
Write-Host "  e virar funnel na 443 exporia o ERP inteiro na internet." -ForegroundColor Red
Write-Host "  Pra conferir o que esta exposto: tailscale funnel status" -ForegroundColor Yellow
Write-Host "  Pra tirar do ar:                 tailscale funnel --https=8443 off" -ForegroundColor Yellow
