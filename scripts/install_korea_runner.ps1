# 한국 PC 에 GitHub 자체 실행기(라벨 korea)를 설치한다 (Windows 10/11).
#
# 해외 접속을 막는 시·군 누리집(도서관·평생학습관 등)을 이 PC 가 매일 05:47 에 대신 읽는다 (.github/workflows/korea.yml).
#
# 준비
#   1) Python 3.12 설치 (python.org 설치판 또는 py 실행기). 'Install for all users' 가 아니어도 됨 — 아래에서 처리
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
    [string]$Branch = "claude/upbeat-wozniak-hv3xh9",
    [string]$Dir = "C:\actions-runner-kyeongbuk",
    [switch]$NoSleep  # 전원 연결 상태에서 절전 모드로 들어가지 않게 설정
)
$ErrorActionPreference = "Stop"

function Fail($msg) { Write-Host "`n[중단] $msg" -ForegroundColor Red; exit 1 }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Fail "PowerShell 을 '관리자 권한으로 실행' 한 뒤 다시 실행하세요 (실행기를 서비스로 등록해야 합니다)." }

# 1. Python 찾기. PATH 의 python 은 Microsoft Store 바로가기(WindowsApps)일 수 있어 믿지 않고
#    py 실행기와 흔한 설치 폴더까지 뒤진다
function Find-Python {
    $cands = @()
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike "*WindowsApps*") { $cands += $c.Source }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { $cands += "$exe".Trim() }
    }
    $cands += Get-ChildItem "C:\Program Files\Python3*\python.exe", "C:\Program Files (x86)\Python3*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "C:\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object FullName
    foreach ($p in $cands) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}
$py = Find-Python
if (-not $py) {
    Write-Host "python 명령: $((Get-Command python -ErrorAction SilentlyContinue).Source)"
    Fail "Python 을 찾지 못했습니다. python.org 에서 3.12 설치판을 받아 'Add python.exe to PATH' 를 체크해 설치한 뒤 다시 실행하세요."
}
$pyDir = Split-Path $py
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git -and (Test-Path "C:\Program Files\Git\cmd\git.exe")) { $git = Get-Item "C:\Program Files\Git\cmd\git.exe" }
if (-not $git) { Fail "Git 을 찾지 못했습니다. git-scm.com 에서 Git for Windows 를 설치하세요." }
$gitDir = Split-Path $git.Source
Write-Host "Python: $(& $py --version)  ($py)"
Write-Host "Git:    $(& $git.Source --version)  ($($git.Source))"

# 실행기는 별도 서비스 계정(NETWORK SERVICE)으로 돌아가므로, 내 사용자 폴더에 깐 Python 도 읽을 수 있게 권한을 준다
if ($pyDir -like "*\Users\*") {
    icacls $pyDir /grant "*S-1-5-20:(OI)(CI)RX" /T /Q | Out-Null
    Write-Host "서비스 계정이 $pyDir 를 읽을 수 있게 했습니다."
}

# 수집에 필요한 파이썬 패키지를 미리 설치해 둔다 (작업 때는 확인만 하고 지나감)
$req = Join-Path $env:TEMP "kyeongbuk-requirements.txt"
Invoke-WebRequest "https://raw.githubusercontent.com/thskal17-sudo/kyeongbuk/$Branch/requirements.txt" -OutFile $req
& $py -m pip install -q -r $req
if ($LASTEXITCODE -ne 0) { Fail "파이썬 패키지 설치에 실패했습니다 (위 오류 참고)." }

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

# 실행기가 작업에 넘겨 줄 PATH (.path 파일): 서비스 계정의 PATH 에는 사용자가 깐 Python 이 없으므로 직접 적는다
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
Set-Content -Path ".\.path" -Value "$pyDir;$pyDir\Scripts;$gitDir;$(Split-Path $gitDir)\bin;$machinePath" -Encoding ASCII

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
