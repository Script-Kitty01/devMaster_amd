param([string]$Command)

$ErrorActionPreference = "Stop"

# Create terminal
$body = @{} | ConvertTo-Json
$resp = Invoke-RestMethod -Uri "https://radeon-global.anruicloud.com/instances/u-14073-bcd85560/api/terminals" -Method Post -Body $body -ContentType "application/json"
$name = $resp.name
Write-Host "Terminal: $name"

# Connect WebSocket
Add-Type -AssemblyName System.Net.WebSockets.Client -ErrorAction SilentlyContinue
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ct = New-Object System.Threading.CancellationToken
$uri = "wss://radeon-global.anruicloud.com/instances/u-14073-bcd85560/terminals/websocket/$name`?token=amd-oneclick"
$task = $ws.ConnectAsync($uri, $ct)
$task.Wait(5000) | Out-Null

# Read initial setup
$buffer = New-Object byte[] 65536
$seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$buffer)
$task = $ws.ReceiveAsync($seg, $ct)
$task.Wait(2000) | Out-Null

# Send command
$jsonCmd = '["stdin", "' + $Command.Replace('\', '\\').Replace('"', '\"') + '\n"]'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonCmd)
$seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$bytes)
$task = $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct)
$task.Wait(3000) | Out-Null

# Read output
$output = ""
$sw = [System.Diagnostics.Stopwatch]::StartNew()
while ($sw.ElapsedMilliseconds -lt 10000) {
    try {
        $buffer = New-Object byte[] 65536
        $seg = New-Object System.ArraySegment[byte] -ArgumentList @(,$buffer)
        $task = $ws.ReceiveAsync($seg, $ct)
        if ($task.Wait(2000)) {
            $result = $task.Result
            if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) { break }
            $text = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count)
            $output += $text
        }
    } catch { break }
}

# Parse and display stdout
$output -split '\n' | ForEach-Object {
    if ($_ -match '\["stdout",\s*"(.*)"\]') {
        $text = $matches[1] -replace '\\r\\n', "`n" -replace '\\r', "`n" -replace '\\n', "`n" -replace '\\"', '"'
        Write-Host $text -NoNewline
    }
}

$ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "", $ct) | Out-Null
