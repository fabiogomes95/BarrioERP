# Renova o certificado HTTPS emitido pelo Tailscale pra este PC e reinicia o
# serviço HTTPS pra carregar o certificado novo. Certificados do Tailscale
# (Let's Encrypt) expiram periodicamente — rodar isso preventivamente (ver
# tarefa agendada "BarrioERP-Renovar-Cert", mensal).

$tailscale = "C:\Program Files\Tailscale\tailscale.exe"
$hostname = "gomes-pc.cod-aldebaran.ts.net"
$certDir = "D:\Users\Fabinho\Documents\BarrioERP\backend\certs"
$logFile = "$certDir\renovar-cert.log"

function Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
}

Set-Location $certDir

& $tailscale cert $hostname 2>> $logFile
if ($LASTEXITCODE -ne 0) {
    Log "ERRO: tailscale cert falhou com codigo $LASTEXITCODE"
    exit 1
}

Log "Certificado renovado com sucesso."

Restart-Service BarrioERP-Backend-TLS -ErrorAction SilentlyContinue
if ($?) {
    Log "Servico BarrioERP-Backend-TLS reiniciado com o certificado novo."
} else {
    Log "ERRO: falha ao reiniciar BarrioERP-Backend-TLS."
}
