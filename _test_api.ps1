$body = '{"openid":"test123","onboarding_survey":{"main_issue":"insomnia","sleep_type":"night_owl","stress_level":"high","sound_pref":"ocean","duration_pref":"medium"}}'
Write-Host "Testing POST /api/update-profile with onboarding_survey..."
try {
    $result = Invoke-RestMethod -Uri 'http://82.156.208.245:8090/api/update-profile' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 10
    Write-Host "SUCCESS: $($result | ConvertTo-Json -Compress)"
} catch {
    Write-Host "FAILED: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Host "Response body: $($reader.ReadToEnd())"
    }
}
