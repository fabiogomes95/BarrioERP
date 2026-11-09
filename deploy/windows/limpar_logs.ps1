# Apaga logs antigos da pasta logs\ do BarrioERP.
#
# Os serviços (NSSM) abrem um arquivo novo a cada reinício e nunca apagam os
# velhos — sem isto, a pasta volta a ter centenas de arquivos em poucos meses.
# Mantém os últimos $Dias dias (o bastante pra investigar um problema) e
# nunca toca nos arquivos em uso (service_out.log, service_err.log...).
#
# Roda sozinho pela tarefa agendada "BarrioERP-Limpar-Logs" (dia 1 de cada
# mês, 10h — fora do horário do bar). À mão:
#   powershell -ExecutionPolicy Bypass -File D:\Users\Fabinho\Documents\BarrioERP\deploy\windows\limpar_logs.ps1

param([int]$Dias = 30)

$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$logs = "$root\logs"
$limite = (Get-Date).AddDays(-$Dias)

# Só os arquivos rotacionados (nome com data: service_out-20261107T034432.964.log)
$velhos = Get-ChildItem $logs -File -Filter *.log -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '-\d{8}T\d{6}' -and $_.LastWriteTime -lt $limite }

$mb = [math]::Round((($velhos | Measure-Object Length -Sum).Sum) / 1MB, 1)
$velhos | Remove-Item -Force -ErrorAction SilentlyContinue

# O log da publicação do cardápio cresce sem rotação: guarda só as últimas 2000 linhas
$pub = "$logs\publicar_cardapio.log"
if (Test-Path $pub) {
    $linhas = Get-Content $pub -Encoding utf8
    if ($linhas.Count -gt 2000) { $linhas | Select-Object -Last 2000 | Set-Content $pub -Encoding utf8 }
}

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Limpeza: $(@($velhos).Count) arquivo(s), $mb MB" |
    Out-File "$logs\limpar_logs.log" -Append -Encoding utf8
