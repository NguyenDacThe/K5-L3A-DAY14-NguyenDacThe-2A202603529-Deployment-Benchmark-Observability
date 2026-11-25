param([Parameter(Mandatory=$true)][string]$TaskFile)
$ErrorActionPreference = 'Stop'
Add-Type @'
using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
public class ObservabilityBrowser : IDisposable {
  private ClientWebSocket socket = new ClientWebSocket();
  public void Connect(string url) { socket.ConnectAsync(new Uri(url), CancellationToken.None).GetAwaiter().GetResult(); }
  public void Send(string json) {
    byte[] bytes = Encoding.UTF8.GetBytes(json);
    socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None).GetAwaiter().GetResult();
  }
  public string Receive() {
    var message = new StringBuilder();
    byte[] buffer = new byte[65536];
    WebSocketReceiveResult part;
    do {
      part = socket.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None).GetAwaiter().GetResult();
      message.Append(Encoding.UTF8.GetString(buffer, 0, part.Count));
    } while (!part.EndOfMessage);
    return message.ToString();
  }
  public void Dispose() { socket.Dispose(); }
}
'@
$task = Get-Content -Raw -Encoding utf8 -LiteralPath $TaskFile | ConvertFrom-Json
$pages = Invoke-RestMethod http://localhost:19228/json/list
$browser = New-Object ObservabilityBrowser
$browser.Connect(($pages | Where-Object type -eq 'page' | Select-Object -First 1).webSocketDebuggerUrl)
$script:commandId = 0
function Invoke-BrowserCommand([string]$Method, $Parameters) {
  $script:commandId++
  $command = @{id=$script:commandId;method=$Method;params=$Parameters} | ConvertTo-Json -Compress -Depth 20
  $browser.Send($command)
  do { $message = $browser.Receive() | ConvertFrom-Json } while ($message.id -ne $script:commandId)
  if ($message.error) { throw ($message.error | ConvertTo-Json -Compress) }
  return $message.result
}
try {
  Invoke-BrowserCommand 'Page.enable' @{} | Out-Null
  Invoke-BrowserCommand 'Emulation.setDeviceMetricsOverride' @{width=1800;height=1100;deviceScaleFactor=1;mobile=$false} | Out-Null
  if ($task.url) {
    Invoke-BrowserCommand 'Page.navigate' @{url=$task.url} | Out-Null
    Start-Sleep -Seconds 5
  }
  if ($task.expression) {
    $evaluation = Invoke-BrowserCommand 'Runtime.evaluate' @{expression=$task.expression;returnByValue=$true;awaitPromise=$true}
    $evaluation.result.value | ConvertTo-Json -Depth 8
    Start-Sleep -Seconds 1
  }
  if ($task.output) {
    $shot = Invoke-BrowserCommand 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$false}
    [System.IO.File]::WriteAllBytes((Join-Path (Get-Location) $task.output),[Convert]::FromBase64String($shot.data))
    Write-Output ('Screenshot: ' + $task.output)
  }
  if ($task.close) {
    $browser.Send('{"id":9999,"method":"Browser.close"}')
    Write-Output 'Closed isolated observability browser.'
  }
} finally { $browser.Dispose() }
