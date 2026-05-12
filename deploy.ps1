param(
    [string]$Server = "",
    [string]$User = "root",
    [string]$RemotePath = "/opt/cc_stock"
)

$ErrorActionPreference = "Stop"

if (-not $Server) {
    $Server = Read-Host "请输入云服务器IP或域名"
}
if (-not $Server) {
    Write-Host "错误: 必须指定服务器地址" -ForegroundColor Red
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  A股股票推荐系统 - 一键部署" -ForegroundColor Cyan
Write-Host "  目标服务器: $Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Step 1: Build frontend locally
Write-Host "[1/5] 构建前端..." -ForegroundColor Yellow
Push-Location "$PSScriptRoot/frontend"
npm install --silent
npm run build
Pop-Location
Write-Host "  前端构建完成" -ForegroundColor Green

# Step 2: Package project files (exclude node_modules, .git, __pycache__)
Write-Host "[2/5] 打包项目文件..." -ForegroundColor Yellow
$archive = "$env:TEMP\cc_stock_deploy.zip"
if (Test-Path $archive) { Remove-Item $archive -Force }
Compress-Archive -Path @(
    "$PSScriptRoot/backend",
    "$PSScriptRoot/frontend/dist",
    "$PSScriptRoot/Dockerfile.backend",
    "$PSScriptRoot/Dockerfile.frontend",
    "$PSScriptRoot/docker-compose.yml",
    "$PSScriptRoot/nginx.conf",
    "$PSScriptRoot/.env.prod",
    "$PSScriptRoot/requirements.txt"
) -DestinationPath $archive -Force
Write-Host "  打包完成: $archive" -ForegroundColor Green

# Step 3: Upload to server
Write-Host "[3/5] 上传到服务器..." -ForegroundColor Yellow
ssh $User@$Server "mkdir -p $RemotePath"
scp $archive "${User}@${Server}:${RemotePath}/deploy.zip"
Write-Host "  上传完成" -ForegroundColor Green

# Step 4: Extract on server
Write-Host "[4/5] 服务器解压..." -ForegroundColor Yellow
ssh $User@$Server @"
cd $RemotePath && unzip -o deploy.zip && rm deploy.zip
"@
Write-Host "  解压完成" -ForegroundColor Green

# Step 5: Docker build & start
Write-Host "[5/5] Docker构建并启动..." -ForegroundColor Yellow
ssh $User@$Server @"
cd $RemotePath && docker compose down && docker compose up -d --build
"@
Write-Host "  部署完成!" -ForegroundColor Green

# Cleanup
Remove-Item $archive -Force

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  访问地址: http://$Server" -ForegroundColor Green
Write-Host "  API文档: http://${Server}/api/docs" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
