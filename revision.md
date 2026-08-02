# Client application revision guide

## 1. 검토 기준

이 문서는 Strawberry GraphQL 업그레이드 및 후속 API 아키텍처 리팩터링 이전 버전(`1c7ecea`)과 현재 서버를 비교해, 기존 client application에서 확인하거나 수정해야 할 계약을 정리한다.

결론적으로 REST/GraphQL endpoint와 주요 operation 이름은 대부분 유지되므로 전면적인 client 수정은 필요하지 않다. 다만 사용자 응답 모델, 인증 실패 처리, 오류 응답, 실시간 구독 장애 처리에는 변경이 필요할 수 있다.

## 2. Client 수정 필요 여부

### 2.1 사용자 응답에서 `password` 필드 제거 — 수정 필요

REST의 `UserDisplaySchema`와 GraphQL의 `UserSchema`에서 `password` 필드가 제거되었다. 다음 응답은 이제 `id`, `username`, `email`만 반환한다.

- `POST /create_user`
- `GET /get_user/{user_id}`
- `POST /update_user/{user_id}`
- GraphQL `user`, `users`, 사용자 생성 mutation
- GraphQL `userAddedSubscription`

기존 client가 응답의 `password`를 역직렬화하거나 화면/상태에 저장한다면 해당 필드를 nullable로 바꾸는 방식보다 모델에서 완전히 제거하는 것이 좋다. 사용자 생성·수정 요청의 `password` 입력은 그대로 필요하다.

GraphQL query 또는 subscription selection set에 `password`가 있으면 schema validation error가 발생하므로 반드시 제거한다.

```graphql
query GetUser($userId: Int!) {
  user(userId: $userId) {
    id
    username
    email
  }
}
```

### 2.2 로그인 실패 상태가 `404`에서 `401`로 변경 — 수정 필요 가능성 높음

`POST /login`에서 계정이 없거나 비밀번호가 틀린 경우 모두 다음 계약을 사용한다.

- HTTP status: `401 Unauthorized`
- header: `WWW-Authenticate: Bearer`
- body: `{"detail":"Could not validate credentials"}`

기존 client가 로그인 실패를 `404`로만 처리한다면 `401` 처리로 변경한다. `401`을 수신하면 저장된 access token을 폐기하되, 로그인 화면에서 발생한 `401`은 “아이디 또는 비밀번호를 확인하세요”처럼 표시한다.

### 2.3 REST 오류 응답 확장 — 수정 권장

리소스 미존재와 중복은 각각 `404`, `409`이며 body에 `code`, `request_id`가 추가되었다. DB 또는 broker 장애는 `503 application/problem+json`으로 반환된다.

DB 장애 예시:

```json
{
  "type": "https://example.com/problems/database-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "데이터 서비스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  "code": "DATABASE_UNAVAILABLE",
  "retryable": true,
  "request_id": "..."
}
```

Client는 문자열 `detail`보다 `code`를 기준으로 분기한다.

- `DATABASE_UNAVAILABLE`: `retryable=true`이면 `Retry-After` header를 존중해 재시도 버튼 또는 제한된 자동 재시도를 제공한다.
- `BROKER_UNAVAILABLE`: `operation_committed`를 반드시 확인한다. `true`이면 본 작업은 이미 DB에 반영되었으므로 mutation을 자동 재전송하지 말고 데이터를 다시 조회한다.
- `RESOURCE_NOT_FOUND`: 찾을 수 없음 화면 또는 목록 새로고침을 제공한다.
- `CONFLICT`: 중복 입력을 사용자에게 알리고 입력 수정을 유도한다.
- `request_id`: 사용자에게 표시하거나 로그에 남겨 서버 문의 시 전달할 수 있게 한다.

### 2.4 GraphQL 오류 extensions 처리 — 수정 권장

GraphQL은 transport가 성공하면 HTTP `200`이어도 `errors` 배열을 반환할 수 있다. 따라서 HTTP status만으로 성공을 판단하지 않는다.

```json
{
  "data": {"user": null},
  "errors": [{
    "message": "...",
    "extensions": {
      "code": "DATABASE_UNAVAILABLE",
      "retryable": true,
      "request_id": "..."
    }
  }]
}
```

Broker publish가 실패했지만 mutation 자체가 저장된 경우에는 `extensions.code="BROKER_UNAVAILABLE"`, `operation_committed=true`, `retryable=false`가 반환된다. 이 경우 mutation 재호출은 중복 생성 가능성이 있으므로 금지하고 query로 결과를 재조회한다.

### 2.5 GraphQL WebSocket — 연결 방식 유지, 장애 처리 보강 권장

endpoint는 계속 `/graphql`이고 `graphql-transport-ws`와 구형 `graphql-ws` protocol을 모두 지원한다. 가능하면 client를 `graphql-transport-ws`로 설정한다. Redis가 중단되면 subscription에 `BROKER_UNAVAILABLE` 오류가 발생할 수 있으므로 다음 정책을 권장한다.

1. 실시간 연결 중단 상태를 사용자에게 표시한다.
2. exponential backoff와 jitter로 WebSocket을 재연결한다.
3. 재연결 후 누락 이벤트가 있을 수 있으므로 관련 query를 다시 실행한다.
4. mutation에서 `operation_committed=true`를 받으면 mutation을 반복하지 않는다.

### 2.6 상태 확인 endpoint 추가 — client/운영 도구에서 활용 권장

- `GET /health/live`: 프로세스 응답 여부. 정상 시 `200 {"status":"ok"}`
- `GET /health/ready`: DB와 broker가 모두 준비된 경우에만 `200`; 하나라도 중단되면 `503`

일반 사용자 client가 매 요청 전에 readiness를 호출할 필요는 없다. 초기 연결 진단, 관리 화면, 배포 health check에서 사용한다.

## 3. Client 연동 검증 준비

아래 명령은 Windows PowerShell 기준이며 서버 주소를 `$Server` 변수로 통일한다.

```powershell
cd G:\OpenAI\graphql-server
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

별도 PowerShell 창에서:

```powershell
$Server = "http://127.0.0.1:8000"
```

Redis backend를 사용하는 경우 `.env`에 `BROADCAST_URL=redis://localhost:6379`를 설정하고 Redis를 먼저 실행한다.

```powershell
docker start graphql-redis
docker exec graphql-redis redis-cli ping
```

## 4. REST 기능 검증 명령

### 4.1 서버와 dependency 상태

```powershell
Invoke-RestMethod "$Server/health/live"
Invoke-RestMethod "$Server/health/ready"
```

### 4.2 사용자 생성

테스트할 때마다 충돌하지 않도록 고유한 사용자 이름을 만든다.

```powershell
$Suffix = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$Username = "client_test_$Suffix"
$Email = "$Username@example.com"
$Password = "Client-Test-Password-123!"

$Created = Invoke-RestMethod `
  -Method Post `
  -Uri "$Server/create_user" `
  -ContentType "application/json" `
  -Body (@{
    username = $Username
    email = $Email
    password = $Password
  } | ConvertTo-Json)

$Created | ConvertTo-Json
```

출력에 `password`가 없어야 한다.

### 4.3 로그인과 Bearer token 발급

`/login`은 JSON이 아니라 `application/x-www-form-urlencoded` 형식이다.

```powershell
$TokenResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "$Server/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{ username = $Username; password = $Password }

$Token = $TokenResponse.access_token
$AuthHeaders = @{ Authorization = "Bearer $Token" }
$TokenResponse | ConvertTo-Json
```

잘못된 비밀번호가 `401`인지 확인한다.

```powershell
try {
  Invoke-WebRequest `
    -Method Post `
    -Uri "$Server/login" `
    -ContentType "application/x-www-form-urlencoded" `
    -Body @{ username = $Username; password = "wrong-password" }
} catch {
  $_.Exception.Response.StatusCode.value__
  $_.ErrorDetails.Message
}
```

### 4.4 사용자 조회와 수정

```powershell
$User = Invoke-RestMethod "$Server/get_user/$($Created.id)"
$User | ConvertTo-Json

$Updated = Invoke-RestMethod `
  -Method Post `
  -Uri "$Server/update_user/$($Created.id)" `
  -ContentType "application/json" `
  -Body (@{
    username = $Username
    email = "updated_$Email"
    password = $Password
  } | ConvertTo-Json)

$Updated | ConvertTo-Json
```

### 4.5 인증된 사용자 삭제

삭제 검증은 GraphQL 테스트까지 끝낸 후 마지막에 실행한다.

```powershell
Invoke-WebRequest `
  -Method Delete `
  -Uri "$Server/$($Created.id)" `
  -Headers $AuthHeaders
```

정상 응답은 `204 No Content`다.

## 5. GraphQL 기능 검증 명령

### 5.1 Query smoke test와 사용자 조회

```powershell
$SmokeBody = @{ query = '{ __typename }' } | ConvertTo-Json
Invoke-RestMethod `
  -Method Post `
  -Uri "$Server/graphql" `
  -ContentType "application/json" `
  -Body $SmokeBody | ConvertTo-Json -Depth 10

$QueryBody = @{
  query = 'query($userId: Int!) { user(userId: $userId) { id username email } }'
  variables = @{ userId = [int]$Created.id }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "$Server/graphql" `
  -ContentType "application/json" `
  -Body $QueryBody | ConvertTo-Json -Depth 10
```

### 5.2 인증된 message mutation

```powershell
$MessageMutation = @{
  query = 'mutation($tid: Int!) { messages(tid: $tid) { id tid text } }'
  variables = @{ tid = 99 }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "$Server/graphql" `
  -Headers $AuthHeaders `
  -ContentType "application/json" `
  -Body $MessageMutation | ConvertTo-Json -Depth 10
```

GraphQL 응답은 항상 `errors` 존재 여부도 확인한다.

### 5.3 다중 파일 upload

PowerShell의 `curl` alias 충돌을 피하려고 `curl.exe`를 사용한다.

```powershell
Set-Content -Path "$env:TEMP\graphql-file-a.txt" -Value "file-a"
Set-Content -Path "$env:TEMP\graphql-file-b.txt" -Value "file-b"

curl.exe "$Server/graphql" `
  -H "Authorization: Bearer $Token" `
  -F 'operations={"query":"mutation($files: [Upload!]!) { readFiles(files: $files) }","variables":{"files":[null,null]}}' `
  -F 'map={"0":["variables.files.0"],"1":["variables.files.1"]}' `
  -F "0=@$env:TEMP\graphql-file-a.txt" `
  -F "1=@$env:TEMP\graphql-file-b.txt"
```

### 5.4 Subscription

`wscat`이 없다면 Node.js 환경에서 다음 명령으로 실행할 수 있다.

```powershell
npx wscat -c ws://127.0.0.1:8000/graphql -s graphql-transport-ws
```

연결 후 아래 메시지를 순서대로 입력한다.

```json
{"type":"connection_init","payload":{}}
```

```json
{"id":"1","type":"subscribe","payload":{"query":"subscription { messageAddedSubscription { id tid text } }"}}
```

다른 PowerShell 창에서 5.2의 message mutation을 실행하면 subscription 창에 이벤트가 도착해야 한다. 종료할 때는 다음을 입력한다.

```json
{"id":"1","type":"complete"}
```

## 6. 장애 처리 검증

### 6.1 Redis 중단

Redis backend로 서버를 실행한 뒤 Redis를 중지한다.

```powershell
docker stop graphql-redis
Invoke-WebRequest "$Server/health/ready" -SkipHttpErrorCheck | Select-Object StatusCode, Content
```

Windows PowerShell 5처럼 `-SkipHttpErrorCheck`가 없다면:

```powershell
try { Invoke-WebRequest "$Server/health/ready" } catch {
  $_.Exception.Response.StatusCode.value__
  $_.ErrorDetails.Message
}
```

기대 결과는 readiness `503`, `broker="unavailable"`이다. 이 상태에서 message mutation을 실행하면 GraphQL `errors[0].extensions`에 다음 값이 있어야 한다.

```json
{
  "code": "BROKER_UNAVAILABLE",
  "operation_committed": true,
  "retryable": false
}
```

이 응답을 받은 client가 mutation을 자동 재시도하지 않고 query로 데이터를 새로 읽는지 확인한다. 검증 후 Redis와 서버를 재시작한다.

```powershell
docker start graphql-redis
```

### 6.2 DB 중단

실제 운영 DB를 중단하지 말고 로컬/테스트 DB에서만 수행한다. DB 연결을 끊은 상태에서도 `/health/live`는 `200`, `/health/ready`는 `503`이어야 한다. REST 요청에는 `503`과 `code="DATABASE_UNAVAILABLE"`, GraphQL 요청에는 HTTP `200` 내부의 `errors[].extensions.code="DATABASE_UNAVAILABLE"`가 반환되어야 한다. Client가 `retryable=true`를 인식하고 중복 요청 위험이 없는 조회만 제한적으로 재시도하는지 확인한다.

## 7. Client 최종 체크리스트

- 사용자 응답 타입과 GraphQL selection set에서 `password`를 제거했다.
- 로그인 실패를 `401`로 처리한다.
- GraphQL HTTP `200`에서도 `errors`를 검사한다.
- REST/GraphQL 모두 오류 `code`를 기준으로 분기한다.
- `request_id`를 진단 로그에 남긴다.
- `retryable`과 `Retry-After`를 재시도 정책에 반영한다.
- `operation_committed=true`인 mutation은 재전송하지 않는다.
- subscription 재연결 후 query로 누락 가능 데이터를 동기화한다.
- `/health/ready`를 client 진단 또는 배포 점검에 활용한다.
