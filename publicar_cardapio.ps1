# Publica o cardápio no GitHub Pages — a cópia que fica SEMPRE no ar, mesmo
# com este PC desligado.
#
# COMO FUNCIONA:
#   A página do GitHub tenta buscar o cardápio ao vivo neste PC (via Funnel).
#   Se o PC não responder, ela usa o menu.json publicado aqui e o pedido vai
#   só pelo WhatsApp. Este script mantém essa cópia em dia: pega o cardápio
#   do serviço local, copia a página/logo de public_menu_static\ e só faz
#   commit/push se algo mudou (preço, item novo, item esgotado, a página...).
#
# Roda sozinho pela tarefa agendada "BarrioERP-Publicar-Cardapio" (a cada
# 10 min). Pra publicar na hora (ex: acabou de mudar preço), rode à mão:
#   powershell -ExecutionPolicy Bypass -File D:\Users\Fabinho\Documents\BarrioERP\publicar_cardapio.ps1

$root = "D:\Users\Fabinho\Documents\BarrioERP"
$site = "D:\Users\Fabinho\Documents\recanto-cardapio-site"   # clone do repositório do site
$log  = "$root\publicar_cardapio.log"
$api  = "http://127.0.0.1:8090/api/cardapio/matriz"

function Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Out-File -FilePath $log -Append -Encoding utf8
}

if (-not (Test-Path "$site\.git")) {
    Log "ERRO: repositório do site não encontrado em $site"
    exit 1
}

# curl.exe grava os bytes exatos (UTF-8) — Invoke-WebRequest do PowerShell 5.1
# erra a acentuação quando a resposta não informa o charset
$tmp = "$site\menu.json.tmp"
& curl.exe -s -f --max-time 15 -o $tmp $api
if ($LASTEXITCODE -ne 0) {
    # Serviço do cardápio parado: NÃO sobrescreve a cópia publicada
    Remove-Item $tmp -ErrorAction SilentlyContinue
    Log "Cardápio local não respondeu (curl $LASTEXITCODE) — mantida a cópia publicada."
    exit 0
}
Move-Item $tmp "$site\menu.json" -Force

Copy-Item "$root\public_menu_static\index.html" "$site\index.html" -Force
Copy-Item "$root\public_menu_static\*.png" $site -Force   # logo + ícones (aba / tela inicial)
if (-not (Test-Path "$site\.nojekyll")) { New-Item "$site\.nojekyll" -ItemType File | Out-Null }

git -C $site add -A
git -C $site diff --cached --quiet
if ($LASTEXITCODE -eq 0) { exit 0 }   # nada mudou

git -C $site commit -q -m "Atualiza cardápio ($(Get-Date -Format 'dd/MM HH:mm'))"
git -C $site push -q 2>> $log
if ($LASTEXITCODE -ne 0) {
    Log "ERRO: push falhou (código $LASTEXITCODE) — tenta de novo na próxima rodada."
    exit 1
}
Log "Cardápio publicado."
