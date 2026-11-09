# Testa se o backup do banco RESTAURA de verdade.
#
# Restaura o último barrio_dump.sql (gerado pelo backup diário) num banco
# TEMPORÁRIO separado, compara a quantidade de linhas de cada tabela com o
# banco real e apaga o temporário no fim. O banco do bar não é alterado.
#
# Como as contagens do banco real mudam durante o dia (comandas novas), uma
# tabela com MAIS linhas no banco real que no backup é normal; o teste só
# reprova se o restore falhar, se faltar tabela ou se o backup tiver mais
# linhas que o real (sinal de dado apagado/perdido).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File D:\Users\Fabinho\Documents\BarrioERP\deploy\windows\testar_backup.ps1
#   (opcional) -Dump "G:\Meu Drive\BarrioERP-Backup\barrio_dump.sql"  → testa a cópia do Drive

param(
    [string]$Dump = "D:\Users\Fabinho\Documents\BarrioERP-DB-Backup\barrio_dump.sql"
)

$ErrorActionPreference = 'Continue'   # erros checados por $LASTEXITCODE (stderr do psql não é erro)
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$bin  = "C:\Program Files\PostgreSQL\16\bin"
$log  = "$root\logs\testar_backup.log"
New-Item -ItemType Directory -Force "$root\logs" | Out-Null

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Host $line
    $line | Out-File $log -Append -Encoding utf8
}

# Credenciais do mesmo .env que o backend usa (nunca impressas)
$cfg = @{}
Get-Content "$root\backend\.env" | ForEach-Object {
    if ($_ -match '^\s*(POSTGRES_[A-Z_]+)\s*=\s*(.*?)\s*$') { $cfg[$matches[1]] = $matches[2].Trim('"') }
}
$conn = @("--host=$($cfg.POSTGRES_HOST)", "--port=$($cfg.POSTGRES_PORT)", "--username=$($cfg.POSTGRES_USER)")
$real = $cfg.POSTGRES_DB
$temp = "barrio_teste_restore"
$env:PGPASSWORD = $cfg.POSTGRES_PASSWORD

function Psql($db, $sql) {
    $out = & "$bin\psql.exe" @conn --dbname=$db -X -A -t -v ON_ERROR_STOP=1 -c $sql 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($out | Out-String) }
    return $out
}

# Contagem exata de linhas de todas as tabelas do schema public
$countSql = @"
SELECT string_agg(format('SELECT %L AS t, count(*) AS n FROM public.%I', tablename, tablename), ' UNION ALL ')
FROM pg_tables WHERE schemaname = 'public'
"@
function Counts($db) {
    $q = (Psql $db $countSql) -join ''
    $h = @{}
    Psql $db $q | ForEach-Object { $t, $n = $_ -split '\|'; if ($t) { $h[$t] = [int64]$n } }
    return $h
}

$ok = $true
try {
    if (-not (Test-Path $Dump)) { throw "Arquivo de backup não encontrado: $Dump" }
    $idade = (Get-Date) - (Get-Item $Dump).LastWriteTime
    Log "Testando $Dump (gerado há $([int]$idade.TotalHours)h, $([math]::Round((Get-Item $Dump).Length/1MB,1)) MB)"
    if ($idade.TotalHours -gt 48) { Log "AVISO: backup com mais de 48h — o backup diário pode estar parado."; $ok = $false }

    & "$bin\dropdb.exe" @conn --if-exists $temp 2>&1 | Out-Null
    & "$bin\createdb.exe" @conn $temp
    if ($LASTEXITCODE -ne 0) { throw "createdb falhou" }

    $restore = & "$bin\psql.exe" @conn --dbname=$temp -X -q -v ON_ERROR_STOP=1 -f $Dump 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Restore falhou:`n$($restore | Select-Object -Last 5 | Out-String)" }
    Log "Restore concluído sem erros."

    $a = Counts $real
    $b = Counts $temp
    foreach ($t in ($a.Keys | Sort-Object)) {
        if (-not $b.ContainsKey($t)) { Log "  FALTA a tabela $t no backup"; $ok = $false; continue }
        $flag = if ($b[$t] -gt $a[$t]) { $ok = $false; '  << backup tem MAIS linhas que o real' } else { '' }
        if ($a[$t] -ne $b[$t] -or $flag) { Log ("  {0,-28} real {1,8}  backup {2,8}{3}" -f $t, $a[$t], $b[$t], $flag) }
    }
    $total = ($b.Values | Measure-Object -Sum).Sum
    Log "Tabelas: $($b.Count) no backup / $($a.Count) no banco real. Linhas restauradas: $total."
}
catch {
    $ok = $false
    Log "ERRO: $($_.Exception.Message)"
}
finally {
    & "$bin\dropdb.exe" @conn --if-exists $temp 2>&1 | Out-Null
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

if ($ok) { Log "RESULTADO: OK — o backup restaura." ; exit 0 }
else     { Log "RESULTADO: FALHOU — ver linhas acima."; exit 1 }
