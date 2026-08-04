Write-Host "=== 测试 1: survey.js 用的 api.post 方式 ==="
$body1 = '{"openid":"test123","profile":{"latest":{"bedtime":"23:30","wake_time":"7:00","sleep_latency":30,"total_duration":420,"awake_times":1},"last_survey":"2026-05-11T00:00:00Z"}}'
Write-Host "Request: $body1"
try {
    $result1 = Invoke-RestMethod -Uri 'http://82.156.208.245:8090/api/update-profile' -Method Post -Body $body1 -ContentType 'application/json' -TimeoutSec 10
    Write-Host "RESULT: $($result1 | ConvertTo-Json -Compress)"
} catch {
    Write-Host "FAILED: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host "Response: $($reader.ReadToEnd())"
    }
}

Write-Host ""
Write-Host "=== 测试 2: survey.js 第二个请求 (history) ==="
$body2 = '{"openid":"test123","profile":{"history":[{"date":"2026-05-11","wm_score":0,"total_duration":420,"bedtime":"23:30","sleep_latency":30,"awake_times":1}]}}'
Write-Host "Request: $body2"
try {
    $result2 = Invoke-RestMethod -Uri 'http://82.156.208.245:8090/api/update-profile' -Method Post -Body $body2 -ContentType 'application/json' -TimeoutSec 10
    Write-Host "RESULT: $($result2 | ConvertTo-Json -Compress)"
} catch {
    Write-Host "FAILED: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host "Response: $($reader.ReadToEnd())"
    }
}
