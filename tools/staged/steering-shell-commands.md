# 셸 명령 작성 규칙 (Windows / PowerShell)

## 최우선 규칙 세 개

1. **파일을 읽거나 코드를 검색할 때 셸을 쓰지 않는다. 예외 없다.**
   - 내용 검색 → `grep_search` 도구
   - 파일 읽기 → `read_file` 도구
   - 파일 찾기 → `file_search` 도구
2. **셸 명령에 쉼표를 쓰지 않는다.** 괄호 안 메서드 인자(`Substring(0,200)`)는 예외다.
   그 외 모든 쉼표는 승인 요청을 유발한다. 파라미터 값 목록, 속성 이름 목록,
   `-f` 연산자 오퍼랜드 전부 포함이다.
3. **차단되면 우회하지 않는다.** 사용자에게 보고하고 판단을 받는다.

아래는 상세 설명이다.

이 워크스페이스의 셸 실행에는 두 개의 통제 장치가 있다.

- `~/.kiro/settings/permissions.yaml` — Kiro 권한 엔진. 세그먼트 단위 glob 매칭
- `.kiro/hooks/shell-gate.json` → `C:\Users\Mickey\.kiro-guards\kiro-shell-gate.ps1` — 훅 게이트

레거시 `kiroAgent.trustedCommands` / `commandDenylist` 레이어는 제거했다.
prefix 매칭이 명령 체인 전체를 신뢰하게 만들고, substring 블랙리스트가 코드 검색까지
막는 문제가 있었다. 이 키들을 다시 추가하지 않는다.

## 작업 디렉터리를 명시하지 않는다

`fs_read` deny 규칙 때문에 셸 도구에 작업 디렉터리를 명시하면 거부된다.
cwd를 비워두면 워크스페이스 루트에서 실행된다. 하위 디렉터리가 필요하면
`Set-Location <경로>; <명령>` 형태를 쓴다.

## 권한 엔진 때문에 못 쓰는 명령

아래는 `permissions.yaml` 의 allow 규칙으로 덮을 수 없는 상위 `ask` 규칙에 걸린다.
`shell` 에 `match: ["*"]` 를 두고 워크스페이스 스코프에 `git *` allow가 있어도 뚫리지 않는다.
`match` 패턴을 고쳐서 해결하려 하지 말고 대체 수단을 쓴다.

| 쓰지 말 것 | 대신 쓸 것 |
|---|---|
| `git grep` | `grep_search` 도구 |
| `git ls-files` | `file_search` 도구 |

## 파일 읽기와 코드 검색은 셸을 쓰지 않는다

**예외 없는 규칙이다.** 셸로 파일을 읽거나 검색하지 않는다. 도구를 쓴다.

| 하려는 일 | 쓸 것 |
|---|---|
| 코드/문자열 검색 | `grep_search` |
| 파일 내용 읽기 | `read_file` |
| 파일 경로 찾기 | `file_search` |
| 디렉터리 구조 파악 | `list_directory` |

셸에서 아래 cmdlet을 위 용도로 쓰지 않는다.

- `Get-Content` — `read_file` 을 쓴다
- `Select-String` — `grep_search` 를 쓴다
- `Get-ChildItem` (파일 찾기/목록 목적) — `file_search` 또는 `list_directory` 를 쓴다
- `git grep`, `git ls-files` — 위 도구를 쓴다
- `Where-Object` / `Sort-Object` / `Format-Table` 로 파일 목록을 가공하는 파이프라인

도구는 셸 평가를 거치지 않는다. 그래서 tree-sitter 파싱 에러도, 승인 요청도,
게이트 판정도 발생하지 않는다. 이 규칙 하나가 지금까지 반복된 프롬프트의
대부분을 없앤다.

셸은 이런 용도로만 쓴다. `flutter` / `dart` / `npm` 실행, `git status` / `log` /
`diff` / `show` / `add` / `commit`, 프로세스나 포트 확인처럼 도구로 대체할 수 없는 작업.

정말 셸로 파일을 봐야 하는 예외 상황이면(예: 도구가 읽지 못하는 바이너리 크기 확인)
먼저 사용자에게 이유를 말하고 판단을 받는다.

## 파라미터 인자에 쉼표를 쓰지 않는다

**확인된 원인.** 권한 엔진은 셸 명령을 tree-sitter PowerShell 문법으로 파싱한다.
쉼표로 나열한 배열 인자를 파싱하지 못하고 `missing node` 에러를 낸다. 파싱이
실패하면 규칙 평가를 못 하므로 기본값 `ask` 로 떨어져 승인 요청이 뜬다.
`permissions.yaml` 을 어떻게 고쳐도 해결되지 않는다.

로그 증거 (`~/.kiro/logs/<최신>/kiro.log`):

```
[PolicyEngine] evaluateShell: tree-sitter parse errors for "Get-ChildItem -Path"
  ["Parse error at position 23: missing node"]
```

position 23이 정확히 쉼표 위치다.

쉼표 하나당 파싱 에러 하나가 정확히 대응한다. 검증된 사례:

| 명령 | 쉼표 위치 | 로그의 에러 위치 |
|---|---|---|
| `Get-ChildItem -Path lib,test ...` | 23 | 23 |
| `... -Path lib,functions/src ... -Include *.dart,*.ts` | 23, 68 | 23, 68 |
| `... \| Format-Table -AutoSize Filename,LineNumber,Line` (len 176) | 160, 171 | 160, 171 |

**경로 인자만의 문제가 아니다.** 어느 위치의 쉼표든 걸린다.

```powershell
# 나쁨 - 파라미터 값 목록
Get-ChildItem -Path lib,test -Recurse -File
Get-ChildItem -Path lib -Recurse -Include *.dart,*.ts
Select-String -Path a.dart,b.dart -Pattern 'x'

# 나쁨 - 속성 이름 목록 (자주 놓치는 부분)
... | Format-Table -AutoSize Filename,LineNumber,Line
... | Select-Object Name,Length,LastWriteTime
... | Sort-Object Name,Length

# 나쁨 - -f 연산자 오퍼랜드
... | ForEach-Object { "{0}:{1}" -f $_.Name, $_.Length }

# 좋음 - 값을 하나만 넘긴다
Get-ChildItem lib -Recurse -File -Filter *.dart

# 좋음 - 속성이 여럿이면 문자열 결합으로 만든다
... | ForEach-Object { $_.Filename + ':' + $_.LineNumber + ' ' + $_.Line }

# 좋음 - 서식 지정을 생략하고 기본 출력을 쓴다
... | Select-Object -First 40 | Out-String -Width 200
```

메서드 호출 안의 쉼표(`Substring(0,200)`, `[Math]::Min(1,2)`, `Round($x,1)`)는
문제가 없다. 괄호 안에 있으면 파서가 처리한다.

여러 경로나 여러 확장자를 봐야 하면 셸을 쓰지 말고 `grep_search` / `file_search`
도구를 쓴다. 그게 이 문제 전체를 없애는 방법이다.

## 명령을 짧고 단순하게 유지한다

`foreach`, `try/catch`, `if/else` 를 섞은 긴 한 줄은 프롬프트를 유발한다.
개별 cmdlet은 통과하는데 그것들을 엮은 400자짜리 명령은 걸린다.

로그(`~/.kiro/logs/<최신>/kiro.log`)에 `[PolicyEngine] evaluateShell: tree-sitter
parse errors` 가 남는다. 권한 엔진이 PowerShell을 tree-sitter로 파싱하는데,
파싱이 실패한 명령과 프롬프트가 뜬 명령이 상관관계를 보인다. 인과로 확정되지는
않았다. 파싱 에러가 났는데 통과한 명령도 있다.

- 한 번에 한 가지만 확인한다. 여러 검사를 `;` 로 이어붙이지 않는다
- 파이프 단계를 줄인다. 중간 결과가 필요하면 나눠서 실행한다

## 통과가 확인된 것들

실제 실행으로 검증된 것만 나열한다.

- `Get-ChildItem`, `Get-Content`, `Get-Process`, `Get-CimInstance`, `Get-NetTCPConnection`,
  `Get-FileHash`
- `Select-String`, `Select-Object`, `Measure-Object`, `ForEach-Object`, `Format-Table`
- `Write-Output`, `Test-Path`
- `git show`, `git ls-files`(로그 조회용으로는 걸림 — 위 표 참고)
- `flutter run`, `flutter test`, `flutter pub get`, `npm install`
- `New-Object`, `[System.IO.File]::ReadAllBytes` 등 .NET 정적 메서드 호출
- 변수 대입 (`$x = ...`), 여는 괄호로 시작하는 서브식
- script block 내부의 중첩 파이프, 인용부호 안의 `|` (`-Pattern 'a|b'`)

## 검증 안 된 것들

통과할 것으로 추정하지만 테스트하지 않았다. 걸릴 수 있다고 가정한다.

- `dart`, `npm`(install 외), `git status`, `git diff`, `git log`
- `Where-Object`, `Sort-Object`, `Out-String`, `Format-List`, `Join-Path`, `Get-Item`

## shell-gate 훅이 차단하는 것

판정 기록은 `C:\Users\Mickey\.kiro-guards\logs\shell-gate.log`.
차단되면 stderr로 사유가 온다.

- 파일/디렉터리 파괴 — `Remove-Item` 계열, .NET `Delete`/`Move`/`WriteAll*`
- 외부 전송 — `git push`, 네트워크 cmdlet, .NET 네트워크 API, `publish`/`deploy`,
  클라우드 CLI, `scp`/`ssh`/`rsync`
- 외부 권한 부여 — IAM 바인딩, 방화벽 규칙, 원격 접속 허용, 로컬 계정·ACL 변경,
  `authorized_keys`
- 비밀 파일 경로 참조 — `.env`, `key.properties`, `*.jks`, `*.pem`,
  `google-services.json`, `GoogleService-Info.plist`
- 임의 코드 실행 — `Invoke-Expression`, `Add-Type`, `npx`, `node -e`, `python -c`,
  `dart run` / `pub run`
- 감시 장치 변조 — `.kiro-guards`, `.kiro/hooks`, `.kiro/steering`,
  `.kiro/settings`, `.vscode/settings.json`, PowerShell 프로필

**차단되면 우회하지 않는다.** 다른 cmdlet이나 .NET API로 같은 일을 하려 하지 말고,
사용자에게 무엇이 왜 막혔는지 알리고 판단을 받는다. 파일 삭제는 `delete_file` 도구를 쓴다.

`git push` 도 차단 대상이다. 커밋은 되지만 푸시는 사용자가 직접 해야 한다.

## 감시 장치를 건드리지 않는다

게이트 스크립트가 워크스페이스 밖에 있는 건 의도된 것이다. 감시 장치를 감시 대상의
쓰기 범위 안에 두면 무력화할 수 있다. `permissions.yaml` 이 그 경로들의 쓰기를
거부하고, 게이트도 그 경로를 언급하는 명령을 차단한다.

게이트를 수정해야 하면 `tools/staged/` 에 작성하고 테스트한 뒤, 사용자에게 복사를
요청한다. 직접 배포하려 하지 않는다.

## 스크립트 실행은 커밋된 것만 가능하다

게이트가 대상 스크립트를 실제로 검사한다. `node <파일>`, `npm run <이름>`,
`powershell -File <파일>`, `python <파일>`, `dart <파일>.dart` 가 대상이다.

두 관문을 통과해야 실행된다.

1. git에 커밋되어 있고 수정되지 않은 상태 — 방금 만들거나 고친 스크립트는 실행 불가
2. 내용 스캔 — 네트워크 모듈, `child_process`, 파괴적 fs 호출, 자격증명 접근,
   동적 eval 이 있으면 차단

차단되면 스크립트를 고쳐서 통과시키려 하지 않는다. 파일 내용과 용도를 사용자에게
보고하고 검토를 요청한다. 커밋을 대신 하겠다고 먼저 나서지 않는다.

경로를 찾을 수 없거나 git 확인이 실패하면 차단된다(fail-closed). 이 경우도 사용자에게
보고한다.

예외: `flutter test` / `dart test` 는 커밋 게이트를 적용하지 않는다. 적용하면
테스트 주도 개발이 불가능해지기 때문이다. 테스트 파일도 임의 코드라는 점은 남는 위험이다.

## 새 명령이 프롬프트나 차단을 유발하면

사용자에게 해당 명령과 대체안을 보고하고, 이 파일의 표에 추가할 것을 제안한다.
이 파일은 `permissions.yaml` deny 대상이라 내가 직접 수정할 수 없다.
`tools/staged/steering-shell-commands.md` 에 작성하고 사용자에게 복사를 요청한다.
