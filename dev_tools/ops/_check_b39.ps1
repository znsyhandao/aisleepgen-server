# 检查 B39 机磁盘
$password = "JIztKP80Ez7p" | ConvertTo-SecureString -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $password)

# 用 ssh 命令 + batch 模式避免交互
$sshArgs = @(
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "BatchMode=no",
    "-p", "38474",
    "-t", "root@connect.westd.seetacloud.com",
    "df -h && echo '---' && du -sh /root/* 2>/dev/null | sort -rh | head -20"
)

Write-Host "连接 B39 机..."
$result = & "ssh" $sshArgs 2>&1
Write-Host $result
