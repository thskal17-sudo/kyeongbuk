# 한국 PC 에 GitHub 자체 실행기(라벨 korea)를 설치한다 (Windows 10/11).
#
# 해외 접속을 막는 시·군 누리집(도서관·평생학습관 등)을 이 PC 가 매일 05:47 에 대신 읽는다 (.github/workflows/korea.yml).
#
# 준비
#   1) Python 3.12 설치: "Add python.exe to PATH" + "Install Python for all users" 체크
#   2) Git for Windows 설치 (기본 설정)
#   3) 저장소 Settings → Actions → Runners → New self-hosted runner 화면의
#      'Configure' 칸 명령에 있는 --token 뒤의 값(영문·숫자 29자 안팎)을 복사 (1시간 동안만 유효)
#
# 실행 (PowerShell 을 '관리자 권한으로 실행' 해서)
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\install_korea_runner.ps1 -Token <복사한 토큰>
#
# 지우기: C:\actions-runner-kyeongbuk 에서  .\config.cmd remove --token <Remove 토큰>
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Repo = "https://github.com/thskal17-sudo/kyeongbuk",
    [string]$Dir = "C:\actions-runner-kyeongbuk",
    [switch]$NoSleep  # 전원 연결 상태에서 절전 모드로 들어가지 않게 설정
)
$ErrorActionPreference = "Stop"

function Fail($msg) { Write-Host "`n[중단] $msg" -ForegroundColor Red; exit 1 }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Fail "PowerShell 을 '관리자 권한으로 실행' 한 뒤 다시 실행하세요 (실행기를 서비스로 등록해야 합니다)." }

# 1. Python·Git 확인 (서비스 계정도 쓸 수 있게 '모든 사용자' 설치여야 함)
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py -or $py.Source -like "*WindowsApps*") {
    Fail "Python 을 찾지 못했습니다. python.org 에서 3.12 를 받아 'Add python.exe to PATH' 와 'Install Python for all users' 를 체크해 설치하세요."
}
if ($py.Source -like "*\Users\*") {
    Write-Host "[주의] Python 이 사용자 폴더($($py.Source))에 있습니다. 서비스로 돈 실행기가 못 찾을 수 있으니 'Install Python for all users' 로 다시 설치하는 것을 권합니다." -ForegroundColor Yellow
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "Git 을 찾지 못했습니다. git-scm.com 에서 Git for Windows 를 설치하세요." }
Write-Host "Python: $(& python --version)  /  Git: $(& git --version)"

# 2. 실행기 내려받기 (최신판)
$release = Invoke-RestMethod "https://api.github.com/repos/actions/runner/releases/latest"
$ver = $release.tag_name.TrimStart("v")
$zip = "actions-runner-win-x64-$ver.zip"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Set-Location $Dir
if (-not (Test-Path ".\config.cmd")) {
    Write-Host "실행기 $ver 내려받는 중..."
    Invoke-WebRequest "https://github.com/actions/runner/releases/download/v$ver/$zip" -OutFile $zip
    Expand-Archive $zip -DestinationPath . -Force
    Remove-Item $zip
}

# 3. 등록: 라벨 korea, 서비스로 실행 (PC 를 켜면 자동 시작)
& .\config.cmd --unattended --url $Repo --token $Token --name "$env:COMPUTERNAME-korea" `
    --labels korea --work _work --runasservice --replace
if ($LASTEXITCODE -ne 0) { Fail "실행기 등록에 실패했습니다. 토큰이 만료(1시간)됐으면 New self-hosted runner 화면을 새로 열어 다시 복사하세요." }

# 4. 절전 끄기 (선택)
if ($NoSleep) {
    powercfg /change standby-timeout-ac 0
    powercfg /change hibernate-timeout-ac 0
    Write-Host "전원 연결 시 절전·최대 절전을 껐습니다."
}

Write-Host "`n[완료] 저장소 Settings → Actions → Runners 에 '$env:COMPUTERNAME-korea' 가 Idle(초록)로 보이면 끝입니다." -ForegroundColor Green
Write-Host "매일 05:47 에 해외 차단 사이트를 읽습니다. 바로 시험하려면 Actions → 한국 PC 수집 → Run workflow."
