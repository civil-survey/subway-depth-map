# 웹지도를 GitHub Pages(subway-depth-map 저장소)에 올립니다.
# 사용: 데이터갱신.bat 실행 후 이 파일을 마우스 오른쪽 > PowerShell에서 실행
$ErrorActionPreference = 'Stop'
$src  = $PSScriptRoot
$repo = Join-Path $env:USERPROFILE 'subway-depth-map'
$git  = 'C:\Program Files\Git\cmd\git.exe'
if (-not (Test-Path (Join-Path $repo '.git'))) {
    & 'C:\Program Files\GitHub CLI\gh.exe' repo clone subway-depth-map $repo
}
New-Item -ItemType Directory -Force (Join-Path $repo 'data') | Out-Null
foreach ($f in 'index.html', 'README.md', '사용법.txt', 'build_data.py', '데이터갱신.bat', '좌표보정.csv', '웹에올리기.ps1', 'data\stations.js', 'data\routes.js', 'data\build_report.txt') {
    $p = Join-Path $src $f
    if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination (Join-Path $repo $f) -Force }
}
& $git -C $repo add -A
& $git -C $repo diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host '바뀐 내용이 없습니다.'; exit 0 }
& $git -C $repo commit -m ("데이터 갱신 " + (Get-Date -Format 'yyyy-MM-dd HH:mm'))
& $git -C $repo push
Write-Host '업로드 완료. 1~2분 뒤 사이트에 반영됩니다.'
