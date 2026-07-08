# 同步推送到 Gitee 仓库
# 使用方法: .\push-gitee.ps1

param(
    [string]$Message = ""
)

$GITEE_URL = "https://gitee.com/buxiangqumingzi/han-cast.git"

# 检查是否已添加 gitee 远程源
$remotes = git remote
if ($remotes -notcontains "gitee") {
    Write-Host "添加 Gitee 远程源..." -ForegroundColor Cyan
    git remote add gitee $GITEE_URL
}

# 如果有提交信息，先提交
if ($Message) {
    Write-Host "提交更改: $Message" -ForegroundColor Cyan
    git add .
    git commit -m $Message
}

# 推送到 Gitee
Write-Host "推送到 Gitee..." -ForegroundColor Cyan
git push gitee master

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ 同步完成!" -ForegroundColor Green
} else {
    Write-Host "✗ 推送失败" -ForegroundColor Red
}
