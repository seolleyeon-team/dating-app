# 셸 명령 작성 규칙 (Windows / PowerShell)

이 워크스페이스에서 셸 명령을 실행할 때 아래 규칙을 따른다.

## 승인 프롬프트를 유발하는 명령을 쓰지 않는다

일부 명령은 `permissions.yaml` 의 allow 규칙으로 덮을 수 없는 상위 `ask` 규칙에 걸린다.
`shell` capability에 `match: ["*"]` 를 두고 워크스페이스 스코프에 `git *` allow가 있어도
뚫리지 않는다. 아래 명령은 사용하지 않고 대체 수단을 쓴다.

| 쓰지 말 것 | 대신 쓸 것 |
|---|---|
| `git grep` | `Get-ChildItem -Recurse -File ... \| Select-String -Pattern '...'` |
| `git ls-files` | `Get-ChildItem -Recurse -File \| Where-Object { ... }` |
| `node <script>` | **대체 수단 없음.** 실행 전에 사용자에게 알린다 |

예시:

```powershell
# 나쁨
git grep -n -e onGenerateRoute -- lib/router/app_router.dart

# 좋음
Select-String -Path lib\router\app_router.dart -Pattern 'onGenerateRoute'

# 나쁨
git ls-files | Select-String -Pattern '\.dart$'

# 좋음
Get-ChildItem -Recurse -File -Filter *.dart lib | Select-Object -ExpandProperty FullName
```

## 통과가 확인된 것들

실제 실행으로 검증된 것만 나열한다.

- `Get-ChildItem`, `Get-Content`, `Get-Process`, `Get-CimInstance`, `Get-NetTCPConnection`
- `Select-String`, `Select-Object`, `Measure-Object`, `ForEach-Object`, `Format-Table`
- `Write-Output`, `Test-Path`
- `git show`
- `New-Object`, `[System.IO.File]::ReadAllBytes` 등 .NET 정적 메서드 호출
- 변수 대입 (`$x = ...`), 여는 괄호로 시작하는 서브식 (`(Get-Content ... | Measure-Object).Lines`)
- script block 내부의 중첩 파이프
- 인용부호 안의 `|` (`-Pattern 'a|b'`)

## 검증 안 된 것들

아래는 통과할 것으로 추정하지만 테스트하지 않았다. 걸릴 수 있다고 가정한다.

- `flutter`, `dart`, `npm`, `npx`
- `git status`, `git diff`, `git log`
- `Where-Object`, `Sort-Object`, `Out-String`, `Format-List`, `Join-Path`, `Get-Item`

## deny 규칙에 걸리는 것들

아래는 차단된다. 우회하지 말고, 필요하면 사용자에게 알리고 판단을 받는다.

- `Remove-Item` — 파일 삭제가 필요하면 `delete_file` 도구를 쓴다
- `git push --force`, `git reset --hard`, `git clean -f`
- `.env`, `*.pem`, `*.jks`, `key.properties` 쓰기

`Remove-Item` 이 막혔을 때 `[System.IO.Directory]::Delete` 나 `cmd /c rmdir` 같은
우회 경로를 쓰지 않는다. deny 규칙은 의도된 안전장치다.

## 명령을 짧고 단순하게 유지한다

긴 다중 문장 스크립트는 프롬프트를 유발한다. 개별 cmdlet은 통과하는데
`foreach`, `try/catch`, `if/else` 같은 제어 구문을 섞은 400자짜리 한 줄은 걸린다.
어느 구문이 원인인지는 특정되지 않았다.

- 한 번에 한 가지만 확인한다. 여러 검사를 `;` 로 이어붙이지 않는다
- 제어 구문이 필요하면 스크립트 파일로 만들어 실행하지 말고, 도구(`read_file`,
  `grep_search`)로 대체할 수 있는지 먼저 본다
- 파일 내용 검사나 집계는 셸 대신 `read_file` / `grep_search` 를 쓴다

## shell-gate 훅

`.kiro/hooks/shell-gate.json` + `tools/kiro-shell-gate.ps1` 이 셸 명령을 검사한다.
차단되면 stderr로 사유가 온다. 판정 기록은 `.kiro/hook-logs/shell-gate.log`.

차단 대상:
- 파일/디렉터리 파괴 (`Remove-Item` 계열, .NET Delete/Move/WriteAll*)
- 외부 전송 (`git push`, 네트워크 cmdlet과 .NET 네트워크 API, 배포·publish 명령,
  클라우드 CLI, `scp`/`ssh`/`rsync`)
- 외부 권한 부여 (IAM 바인딩, 방화벽 규칙, 원격 접속 허용, 로컬 계정·ACL 변경,
  `authorized_keys`)
- 비밀 파일 경로 참조 (`.env`, `key.properties`, `*.jks`, `*.pem`,
  `google-services.json`, `GoogleService-Info.plist`)
- 임의 코드 실행 (`Invoke-Expression`, `Add-Type`, `node -e`, `python -c`)

**차단되면 우회하지 않는다.** 다른 cmdlet이나 .NET API로 같은 일을 하려 하지 말고,
사용자에게 무엇이 왜 막혔는지 알리고 판단을 받는다. 파일 삭제는 `delete_file` 도구를 쓴다.

`git push` 도 차단 대상이다. 커밋은 되지만 푸시는 사용자가 직접 해야 한다.

## 새 명령이 프롬프트를 띄우면

사용자에게 해당 명령과 대체안을 보고하고, 이 파일의 표에 추가한다.
`match` 패턴을 고쳐서 해결하려 하지 않는다. 이 부류는 allow 규칙으로 해결되지 않는다.
