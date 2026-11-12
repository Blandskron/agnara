$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$image = 'rabbitmq:4.2.5-alpine@sha256:d4a3806070111cc69130a6542aa4049b612789852ef11fc3862abc94631b2572'
$name = 'agnara-evt01-' + [guid]::NewGuid().ToString('N')
$env:AGNARA_EVT_ADMIN = [guid]::NewGuid().ToString('N')
$env:AGNARA_EVT_PUBLISHER = [guid]::NewGuid().ToString('N')
$env:AGNARA_EVT_DENIED = [guid]::NewGuid().ToString('N')

Push-Location (Join-Path $PSScriptRoot '../..')
try {
    docker run -d --name $name -p 127.0.0.1::5672 -e RABBITMQ_DEFAULT_USER=evt-admin -e "RABBITMQ_DEFAULT_PASS=$env:AGNARA_EVT_ADMIN" $image | Out-Null
    $env:AGNARA_EVT_PORT = ((docker port $name 5672/tcp) -split ':')[-1]
    $deadline = (Get-Date).AddSeconds(60)
    do {
        $ready = & {
            $PSNativeCommandUseErrorActionPreference = $false
            docker exec --user rabbitmq $name sh -c 'test -r /var/lib/rabbitmq/.erlang.cookie && rabbitmq-diagnostics -q check_running' 2>$null | Out-Null
            $LASTEXITCODE -eq 0
        }
        if (-not $ready) { Start-Sleep -Milliseconds 500 }
    } until ($ready -or (Get-Date) -ge $deadline)
    if (-not $ready) {
        docker logs --tail 15 $name
        throw 'RabbitMQ did not start within 60 seconds'
    }

    docker exec $name rabbitmqctl -q add_user evt-publisher $env:AGNARA_EVT_PUBLISHER | Out-Null
    docker exec $name rabbitmqctl -q set_permissions evt-publisher '^$' '^inventory-in$' '^$' | Out-Null
    docker exec $name rabbitmqctl -q add_user evt-denied $env:AGNARA_EVT_DENIED | Out-Null
    docker exec $name rabbitmqctl -q set_permissions evt-denied '^$' '^$' '^$' | Out-Null
    docker exec $name rabbitmqctl -q set_policy evt01 '^inventory$' '{"dead-letter-strategy":"at-least-once"}' --apply-to quorum_queues | Out-Null
    & (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m experiments.events.probe
}
finally {
    $PSNativeCommandUseErrorActionPreference = $false
    docker rm -fv $name 2>$null | Out-Null
    Remove-Item Env:AGNARA_EVT_ADMIN,Env:AGNARA_EVT_PUBLISHER,Env:AGNARA_EVT_DENIED,Env:AGNARA_EVT_PORT -ErrorAction SilentlyContinue
    Pop-Location
}
