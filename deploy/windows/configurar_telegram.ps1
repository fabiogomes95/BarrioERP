# Liga os avisos do Barrio no Telegram (monitor, alertas de dinheiro, resumo da noite).
#
# Pede o token do bot (do @BotFather), confere se ele vale, descobre sozinho o
# número do chat (a partir de um "oi" mandado pro bot) e grava no backend\.env.
# O token só existe na sua tela e no .env — não sai daqui.
#
# Uso (PowerShell normal, não precisa ser Administrador):
#   powershell -ExecutionPolicy Bypass -File D:\Users\Fabinho\Documents\BarrioERP\deploy\windows\configurar_telegram.ps1

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$envFile = (Resolve-Path "$PSScriptRoot\..\..\backend\.env").Path

Write-Host ""
Write-Host "=== Telegram do Barrio ===" -ForegroundColor Cyan
$token = (Read-Host "Cole o token do BotFather e aperte Enter").Trim().Trim('"', "'", '<', '>')

try {
    $me = Invoke-RestMethod "https://api.telegram.org/bot$token/getMe"
} catch {
    Write-Host "Token recusado pelo Telegram. Copie de novo a resposta do @BotFather (numeros:letras) e rode outra vez." -ForegroundColor Red
    exit 1
}
$bot = $me.result.username
Write-Host "Token OK - bot @$bot" -ForegroundColor Green
Write-Host ""
Write-Host "Agora, no Telegram, abra @$bot, aperte INICIAR e mande um 'oi'."
Read-Host "Depois de mandar, aperte Enter aqui"

$chat = $null
for ($i = 0; $i -lt 3 -and -not $chat; $i++) {
    $up = Invoke-RestMethod "https://api.telegram.org/bot$token/getUpdates"
    $ids = foreach ($u in $up.result) {
        if ($u.message) { $u.message.chat.id }
        elseif ($u.my_chat_member) { $u.my_chat_member.chat.id }
    }
    $chat = $ids | Where-Object { $_ } | Select-Object -Last 1
    if (-not $chat) { Start-Sleep -Seconds 3 }
}
if (-not $chat) {
    Write-Host "Nao achei a mensagem. Mande 'oi' pro @$bot e rode o script de novo." -ForegroundColor Red
    exit 1
}
Write-Host "Chat encontrado: $chat" -ForegroundColor Green

# Grava no .env trocando as linhas antigas, se houver. UTF-8 SEM BOM: com BOM
# a primeira variavel do .env deixa de ser lida.
$linhas = [IO.File]::ReadAllLines($envFile) | Where-Object { $_ -notmatch '^\s*ALERT_TELEGRAM_(BOT_TOKEN|CHAT_ID)\s*=' }
$linhas += "ALERT_TELEGRAM_BOT_TOKEN=$token"
$linhas += "ALERT_TELEGRAM_CHAT_ID=$chat"
[IO.File]::WriteAllLines($envFile, [string[]]$linhas, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Gravado em $envFile" -ForegroundColor Green

# Teste com o proprio monitor (mesmo caminho dos avisos de verdade)
Push-Location "$PSScriptRoot\..\..\backend"
& .\.venv\Scripts\python.exe -m app.monitoring --test
Pop-Location
Write-Host ""
Write-Host "Pronto. Chegou a mensagem de teste no Telegram? Entao os avisos estao ligados." -ForegroundColor Cyan
