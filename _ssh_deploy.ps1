# SSH connect with password via plain text pipe
$secpass = ConvertTo-SecureString "AISleepGen20260427cqs103@!" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("ubuntu", $secpass)

# Use SSH.NET-like approach - actually just use ssh command with batch mode
# The problem is Windows SSH doesn't support password on stdin
# Let's try a different approach - create a temporary SSH config

Write-Host "=== Testing server connectivity ==="
try {
    $result = Invoke-RestMethod -Uri "http://82.156.208.245:8090/health" -TimeoutSec 5
    Write-Host "Server API is alive: $($result | ConvertTo-Json -Compress)"
} catch {
    Write-Host "Server API check failed: $($_.Exception.Message)"
}

Write-Host "`nDone. Server is at 82.156.208.245:8090"
