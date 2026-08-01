# Strawberry GraphQL 최신 버전 업그레이드 계획

## 1. 목표와 기준

- 대상: `G:\OpenAI\graphql-server`
- 현재 버전: `strawberry-graphql==0.153.0`
- 목표 버전: `strawberry-graphql==0.322.2` (2026-08-01 기준 PyPI 최신 안정 버전)
- 범위: Strawberry 버전 변경, 최신 버전에서 동작하지 않는 GraphQL 코드 수정, HTTP/파일 업로드/인증/구독 회귀 검증
- 범위 제외: 기능 추가, 데이터 모델·DB 스키마 변경, Strawberry와 직접 관련 없는 전체 프레임워크 현대화

참고 자료:

- PyPI 릴리스: https://pypi.org/project/strawberry-graphql/
- 공식 업그레이드 안내: https://strawberry.rocks/docs/general/upgrades
- FastAPI 통합: https://strawberry.rocks/docs/integrations/fastapi
- 파일 업로드: https://strawberry.rocks/docs/guides/file-upload

## 2. 사전 조사 결과

### 확인된 영향 지점

| 파일 | 현재 사용 API | 예상/확인된 조치 |
| --- | --- | --- |
| `requirements.txt` | `strawberry-graphql==0.153.0` | `0.322.2`로 고정하고 의존성 해석 결과 확인 |
| `api/graphql/schema.py` | `@strawberry.subscription`, 무타입 `info` | 두 subscription resolver의 `info`에 `Info[CustomContext, None]` 또는 순환 참조를 피한 동등 타입 지정 |
| `api/routers/graphql.py` | `GraphQLRouter`, `BaseContext`, 업로드 mutation | `multipart_uploads_enabled=True` 명시; context 타입/의존성 주입 호환성 검증 |
| `api/graphql/resolvers.py` | `Info`, `Upload`, resolver 함수 | 최신 resolver 인자 해석 및 context 접근 검증; 필요하면 구체적인 `Info` 제네릭 타입 적용 |
| `api/graphql/fields.py` | `Upload`, Strawberry type/input | 스키마 생성과 multipart input 타입 회귀 검증 |
| `api/utils/auth.py` | `BasePermission`, `Info`, `info.context.request` | HTTP와 WebSocket에서 request/context 접근 및 permission 실행 검증 |
| `main.py` | router include + 별도 `add_websocket_route` | 최신 `GraphQLRouter`가 HTTP/WS를 함께 처리하는 현재 구성이 중복 라우팅을 만들지 검증하고, 필요하면 단일 router 등록으로 정리 |

### 실제 최신 버전 검증에서 확인된 사항

1. `strawberry-graphql==0.322.2`로 현재 스키마를 import하면 `api/graphql/schema.py`의 `user_added_subscription`에서 즉시 `MissingArgumentsAnnotationsError`가 발생한다. 같은 형태인 `message_added_subscription`도 함께 수정해야 한다.
2. 최신 `GraphQLRouter`에는 `multipart_uploads_enabled` 인자가 존재하며 기본값은 `False`다. 현재 앱은 `Upload` mutation을 제공하므로 `True`를 명시하지 않으면 업로드 요청이 깨진다.
3. `BaseContext`, `GRAPHQL_TRANSPORT_WS_PROTOCOL`, `GRAPHQL_WS_PROTOCOL`, `subscription_protocols`는 0.322.2에도 존재한다. 이 부분은 무조건 교체하지 않고 회귀 테스트 결과에 따라 최소 수정한다.
4. 목표 Strawberry는 Python `>=3.10,<4.0`을 요구한다. 현재 `.venv` 실행 파일은 삭제된 Python 3.10 경로를 참조해 실행되지 않으므로, 재현 가능한 Python 환경을 먼저 복구해야 한다.
5. 별도 Python 3.14 검증 중 `aiohttp==3.8.6`이 빌드되지 않았다. 이는 Strawberry 코드 호환성과 별개의 환경 호환성 문제지만, Python 3.14를 선택할 경우 의존성 갱신 범위가 커진다. 업그레이드 작업은 우선 Python 3.10~3.13의 프로젝트 지원 버전에서 수행한다.

## 3. 구현 순서

### 1단계: 기준선과 실행 환경 고정

1. 변경 전 브랜치/커밋과 `requirements.txt`를 보존한다.
2. Python 3.10~3.13 중 팀의 운영 버전을 명시하고 새 가상환경을 만든다. 기존 `.venv`는 경로가 깨져 있으므로 재사용하지 않는다.
3. 현재 `0.153.0` 상태에서 가능한 스키마 출력과 주요 GraphQL 요청을 기록해 회귀 기준으로 삼는다.
4. 테스트가 없다면 최소 smoke test 파일을 먼저 추가한다. DB 의존 resolver는 repository/broadcast를 fake 또는 mock으로 대체한다.

완료 기준: 기존 스키마의 query/mutation/subscription 목록과 대표 요청·응답을 재현할 수 있다.

### 2단계: 의존성 업그레이드

1. `requirements.txt`의 Strawberry 고정을 `strawberry-graphql==0.322.2`로 변경한다.
2. 새 환경에서 `pip check`를 실행해 `graphql-core`, FastAPI/Starlette 등과의 충돌을 확인한다.
3. 충돌이 있으면 Strawberry에 필요한 최소 범위만 함께 조정한다. 특히 현재 FastAPI `0.89.1`의 동작을 우선 검증하고, 관련 없는 일괄 업그레이드는 분리한다.
4. 깨끗한 환경에서 requirements 전체 설치가 성공하는지 확인한다.

완료 기준: 의존성 설치와 `pip check`가 성공하고 실제 설치된 Strawberry 버전이 `0.322.2`다.

### 3단계: 스키마/구독 타입 호환성 수정

1. `api/graphql/schema.py`에 `Info`를 import한다.
2. `user_added_subscription`과 `message_added_subscription`의 `info` 인자에 명시적 타입을 추가한다.
3. context 타입을 직접 참조하면 순환 import가 생길 수 있으므로, `TYPE_CHECKING`, forward reference 또는 별도 context 모듈 분리 중 가장 작은 변경을 선택한다.
4. `schema.as_str()`을 실행해 전체 SDL 생성이 성공하는지 확인한다.
5. 새 오류가 드러나면 Strawberry 공식 breaking-change 문서와 exception을 기준으로 하나씩 수정하되 public API만 사용한다.

완료 기준: 애플리케이션 import와 Strawberry schema 생성이 경고/예외 없이 성공한다.

### 4단계: FastAPI 라우터와 파일 업로드 수정

1. `api/routers/graphql.py`의 `GraphQLRouter(...)`에 `multipart_uploads_enabled=True`를 추가한다.
2. 업로드 활성화가 의도된 보안 결정임을 주석 또는 운영 문서에 남기고, 인증이 필요한 upload mutation은 기존 `IsAuthenticated`를 유지한다.
3. 단일 파일 `readFile`, 다중 파일 `readFiles`, folder input `readFolder` multipart 요청을 각각 테스트한다.
4. 업로드 크기·파일명·저장 경로 검증은 기존 동작을 바꾸지 않되, 발견되는 보안 문제는 별도 작업으로 기록한다.

완료 기준: 인증된 multipart 요청은 성공하고, 비활성화/인증 실패 경로는 예상한 GraphQL 오류를 반환한다.

### 5단계: context, permission, WebSocket 회귀 수정

1. HTTP 요청에서 `get_context`가 `CustomContext`를 반환하고 `request`, repository, broadcast가 모두 채워지는지 확인한다.
2. `IsAuthenticated.has_permission`에서 `info.context.request`가 HTTP `Request`와 WebSocket 연결 모두에서 유효한지 검증한다.
3. `graphql-transport-ws`를 우선 프로토콜로 subscription 연결, 이벤트 발행, 연결 종료를 테스트한다. 레거시 `graphql-ws` 지원 필요 여부는 실제 클라이언트 기준으로 결정한다.
4. `app.include_router(..., prefix="/graphql")`와 `app.add_websocket_route("/graphql", graphql_router)`의 중복 여부를 route table 및 실제 WS 연결로 확인한다. 중복이면 최신 권장 방식인 router 단일 등록으로 정리한다.
5. broadcast 연결을 앱 lifespan에서 열고 닫아야 하는지는 누수/재연결 테스트 결과에 따라 별도 최소 수정한다.

완료 기준: 인증 query/mutation과 두 subscription이 실제 ASGI client에서 정상 동작하고 연결 종료 후 리소스 경고가 없다.

### 6단계: 전체 회귀 테스트와 문서화

다음 항목을 자동화한다.

- 앱 import 및 `/graphql` route 존재 여부
- SDL snapshot 또는 핵심 field 존재 여부
- `user`, `users`, `messages` query
- `user`, `messages`, 파일 관련 mutation
- 인증 성공/실패 permission 경로
- 단일·다중 multipart 업로드
- `userAddedSubscription`, `messageAddedSubscription` WebSocket 흐름
- 잘못된 입력과 resolver exception의 GraphQL 오류 응답
- 서버 시작/종료 및 broadcast 정리

실행 명령 예시:

```powershell
python -m pip check
python -c "import strawberry, api.graphql.schema; print(api.graphql.schema.schema.as_str())"
python -m pytest
```

완료 기준: 새 환경에서 설치, schema 생성, 자동 테스트가 모두 통과하며 기존 GraphQL SDL의 의도하지 않은 변경이 없다.

## 4. 예상 변경 파일

- 필수: `requirements.txt`
- 필수: `api/graphql/schema.py`
- 필수: `api/routers/graphql.py`
- 검증 결과에 따라: `api/graphql/resolvers.py`, `api/utils/auth.py`, `main.py`
- 신규 권장: `tests/test_graphql_schema.py`, `tests/test_graphql_http.py`, `tests/test_graphql_upload.py`, `tests/test_graphql_subscription.py`

## 5. 위험과 대응

- **0.153.0에서 0.322.2로 큰 폭 업그레이드:** schema import → HTTP → upload → WS 순으로 좁게 검증해 원인을 분리한다.
- **파일 업로드 기본값 변경:** `multipart_uploads_enabled=True`를 명시하고 인증 및 요청 제한을 함께 확인한다.
- **구독 resolver 타입 검사 강화:** 모든 Strawberry resolver 인자에 타입이 있는지 schema 생성 단계에서 검증한다.
- **오래된 FastAPI/Starlette 조합:** 먼저 현 버전과 호환성을 검증하고, 프레임워크 업그레이드가 필요하면 별도 커밋으로 분리한다.
- **고장 난 기존 `.venv`:** 새 환경을 만들고 Python 버전과 설치 절차를 README 또는 개발 문서에 기록한다.
- **DB/메시지 브로커 의존성:** unit test에서는 fake를 사용하고, 최종 단계에서 실제 통합 smoke test를 별도로 수행한다.

## 6. 롤백 전략

1. 의존성 변경, 코드 호환성 수정, 테스트 추가를 서로 분리된 커밋으로 만든다.
2. 배포 전 기존 SDL과 새 SDL을 비교한다.
3. 운영 오류 시 코드 커밋과 `requirements.txt`를 함께 되돌려 `0.153.0` 환경으로 복귀한다.
4. DB migration은 포함하지 않으므로 데이터 롤백은 필요하지 않아야 한다.

## 7. 최종 완료 조건

- `strawberry-graphql==0.322.2`가 깨끗한 지원 Python 환경에 설치된다.
- 앱과 schema import가 성공한다.
- query, mutation, 인증, multipart upload, 두 subscription 테스트가 통과한다.
- GraphQL SDL에 의도하지 않은 breaking change가 없다.
- 실행 환경, 테스트 방법, 업로드 활성화 결정이 문서화되어 있다.
