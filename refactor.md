# API 코드 및 아키텍처 리팩터링 검토

## 1. 검토 범위와 결론

검토 대상은 `api` 아래의 데이터베이스, Dependency Injector 컨테이너, repository, REST router, Strawberry GraphQL schema/resolver/context, 인증, 파일 처리 코드이며, 앱 조립 방식 확인을 위해 `main.py`도 함께 보았다.

현재 코드는 작은 예제 앱으로는 이해하기 쉽지만, 전송 계층(REST/GraphQL), 업무 규칙, 저장소, 인프라가 서로 직접 의존한다. 특히 repository가 GraphQL 전용 `ResponseSchema`를 반환하므로 DB 오류, 중복, 미존재 같은 상태를 계층별로 일관되게 처리하기 어렵다. DB 연결이 끊기면 SQLAlchemy 예외가 그대로 상위로 전파되고, `main.py`가 import 시점에 `create_all()`을 호출하기 때문에 서버가 시작조차 못 할 수 있다.

권장 방향은 대규모 프레임워크 도입이 아니라 다음 네 가지 경계를 명확히 하는 것이다.

1. **Presentation:** REST router와 GraphQL resolver는 입력/출력 변환만 담당한다.
2. **Application:** `UserService` 같은 use-case/service가 업무 흐름과 transaction을 조정한다.
3. **Domain:** 전송 기술과 무관한 entity/value/error를 둔다.
4. **Infrastructure:** SQLAlchemy repository, DB session, broadcaster, 파일 시스템 구현을 둔다.

DB 장애는 infrastructure에서 `DatabaseUnavailableError`로 변환하고, REST와 GraphQL이 각각 안전한 공개 응답으로 매핑하는 것이 핵심이다.

## 2. 우선순위별 발견 사항

### P0 — 즉시 수정할 정확성·보안 문제

#### 2.1 비밀번호가 API 응답과 GraphQL schema에 노출됨

- `api/schemas.py`의 `UserDisplaySchema`가 `password`를 포함한다.
- `api/graphql/fields.py`의 `UserSchema`도 `password`를 공개한다.
- 로그인 외 사용자 조회와 생성 응답에서 password hash가 외부로 반환될 수 있다.

개선:

- 입력 모델 `UserCreate`, `UserPasswordUpdate`와 출력 모델 `UserPublic`을 분리한다.
- REST/GraphQL 출력 타입에서 `password`를 제거한다.
- ORM entity를 그대로 반환하지 말고 service에서 public DTO로 변환한다.
- 기존 클라이언트가 `password` 필드를 사용한다면 즉시 중단시키고 schema breaking change로 공지한다.

#### 2.2 GraphQL 사용자 생성에서 비밀번호를 두 번 해시함

`api/graphql/resolvers.py`의 `create_user`는 `data.password`를 먼저 해시한 뒤 `UserCreateSchema`를 만들고 다시 해시한다. 이 계정은 평문 비밀번호로 로그인할 수 없다.

개선:

- 비밀번호 해시는 `UserService.create_user()` 한 곳에서 정확히 한 번 수행한다.
- REST와 GraphQL 모두 같은 service를 호출한다.
- “저장된 값이 평문과 검증되고 hash 자체를 평문으로 넣으면 검증되지 않는다”는 테스트를 추가한다.

#### 2.3 REST path parameter 이름 불일치

`api/routers/login.py`는 `@router.get("/get_user/{id}")`인데 함수 인자는 `user_id`다. `/{user_id}`로 통일해야 한다. 현재는 path 값이 의도대로 repository에 전달되지 않는다.

#### 2.4 인증 실패 상태와 토큰 검증이 불명확함

- 잘못된 로그인 정보를 `404`로 반환한다. 일반적으로 `401`과 `WWW-Authenticate: Bearer`가 적합하다.
- Authorization 값에서 무조건 `[7:]`을 잘라 Bearer 형식을 엄격히 검증하지 않는다.
- `SECRET_KEY`가 없을 때 시작 시 명확히 실패하지 않는다.
- `datetime.utcnow()`과 로컬 `datetime.now()`를 섞어 만료 시간을 비교한다.
- 토큰 유효 기간이 1년(`525600`분)으로 매우 길다.

개선:

- 설정 객체에서 secret 존재 여부와 알고리즘을 시작 시 검증한다.
- REST는 FastAPI security dependency, GraphQL은 공통 `TokenVerifier`를 사용한다.
- UTC timezone-aware datetime을 사용하고 access token 수명을 단축한다. 장기 세션은 refresh token으로 분리한다.
- 인증 실패 메시지는 계정 존재 여부를 드러내지 않는 동일한 `401` 응답으로 통일한다.

### P1 — DB 장애 처리와 서비스 안정성

#### 2.5 앱 import 시 DB schema 생성

`main.py`에서 container 생성 직후 `db.create_database()`를 실행한다. DB가 중단되면 FastAPI 앱이 생성되지 않아 `/health/live`, `/health/ready` 또는 사용자 친화적인 503 응답을 제공할 수 없다. 여러 인스턴스가 동시에 `create_all()`을 실행하는 것도 배포 안정성에 좋지 않다.

개선:

- schema 변경은 Alembic migration을 배포 단계에서 실행한다.
- 앱 시작은 DB 연결 없이도 최소한 liveness endpoint를 제공할 수 있게 한다.
- lifespan에서 선택적으로 DB readiness를 검사하되 실패했다고 프로세스를 반드시 종료할지는 배포 정책으로 결정한다.
- 일반 권장 정책은 **프로세스는 기동, readiness는 503**이다. Kubernetes/로드밸런서는 해당 인스턴스로 트래픽을 보내지 않고 liveness는 유지한다.

#### 2.6 DB 예외 분류와 공개 오류 계약이 없음

현재 `Database.session()`은 rollback 후 원래 예외를 다시 던진다. repository는 `IntegrityError`만 일부 잡고, `OperationalError`, `DisconnectionError`, `TimeoutError` 등은 그대로 REST/GraphQL 계층까지 전달된다. 결과는 REST 500 또는 구현 세부사항이 섞인 GraphQL error가 될 수 있다.

다음 application error를 정의하는 것이 좋다.

```python
class ApplicationError(Exception):
    code: str


class ResourceNotFoundError(ApplicationError):
    code = "RESOURCE_NOT_FOUND"


class ConflictError(ApplicationError):
    code = "CONFLICT"


class DatabaseUnavailableError(ApplicationError):
    code = "DATABASE_UNAVAILABLE"

    def __init__(self, *, retryable: bool = True):
        self.retryable = retryable
        super().__init__("Database service is temporarily unavailable")
```

SQLAlchemy adapter에서 다음처럼 변환한다.

- `IntegrityError` → `ConflictError`
- `OperationalError`, `DisconnectionError`, DBAPI connection 오류, pool timeout → `DatabaseUnavailableError`
- 미조회 결과 → `ResourceNotFoundError`
- 예상하지 못한 programming/data 오류 → 내부 로그 후 다시 발생시켜 결함으로 구분

중요한 원칙:

- SQL 문, DB URL, host, 계정, 원본 driver 메시지를 사용자에게 반환하지 않는다.
- 원본 예외는 `raise ... from exc`로 보존하고 서버 로그/추적 시스템에만 기록한다.
- 모든 로그에 `request_id` 또는 `correlation_id`를 포함한다.
- rollback은 transaction 경계에서 한 번만 책임진다.

#### 2.7 사용자에게 알릴 DB 장애 응답

REST는 중앙 exception handler에서 RFC 9457 Problem Details 형태의 `503 Service Unavailable`을 반환한다.

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

가능하면 `Retry-After` 헤더를 추가한다. 정확한 복구 시간을 모르면 짧은 고정값을 약속하기보다 클라이언트에 exponential backoff와 jitter를 안내한다.

GraphQL은 transport 자체가 정상 처리된 경우 HTTP 200과 `errors` 배열을 유지하고, 공개 extension을 일관되게 제공한다.

```json
{
  "data": null,
  "errors": [
    {
      "message": "데이터 서비스에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
      "extensions": {
        "code": "DATABASE_UNAVAILABLE",
        "retryable": true,
        "request_id": "..."
      }
    }
  ]
}
```

이를 위해 GraphQL resolver에서 FastAPI `HTTPException`을 던지지 말고 application exception을 Strawberry `GraphQLError` 또는 schema가 정의한 error union으로 매핑한다. 인프라 장애처럼 모든 클라이언트가 공통 처리해야 하는 오류는 `extensions.code`, 사용자의 잘못된 입력이나 충돌처럼 업무적으로 예상되는 오류는 typed result/union을 고려한다.

사용자 안내 문구는 다음 특성을 가져야 한다.

- 장애가 일시적일 가능성과 재시도 가능 여부를 명시한다.
- “MySQL 연결 거부”, host/IP, stack trace 같은 내부 정보를 숨긴다.
- 지원팀 문의에 사용할 `request_id`를 제공한다.
- 쓰기 요청의 결과가 불확실할 수 있으면 무조건 재시도하라고 하지 말고, idempotency key 또는 조회 확인 절차를 안내한다.

#### 2.8 연결 복원 전략

`create_engine()`에 운영 환경별 pool 설정을 명시한다.

- `pool_pre_ping=True`: checkout 전에 죽은 연결 감지
- `pool_recycle`: 서버/프록시 idle timeout보다 짧게 설정
- `pool_timeout`: 무한 대기 방지
- driver connect/read/write timeout

재시도는 다음 조건에서만 제한적으로 적용한다.

- 연결 생성 단계 또는 transaction 시작 전 실패
- 안전한 read나 명시적으로 idempotent한 작업
- 짧은 횟수, exponential backoff + jitter

`commit()`의 결과를 모르는 쓰기 작업은 자동 재시도하면 중복 생성될 수 있다. create API에 idempotency key 또는 업무상 unique key가 없다면 사용자에게 결과 확인을 유도해야 한다. 장애가 지속되면 circuit breaker로 DB 호출을 빠르게 거절하고 503을 반환하는 방안도 트래픽 규모에 따라 적용한다.

#### 2.9 상태 확인 endpoint

- `/health/live`: 프로세스 event loop가 응답하면 200. DB를 확인하지 않는다.
- `/health/ready`: `SELECT 1`을 짧은 timeout으로 실행하고 성공하면 200, 실패하면 503.
- readiness 응답은 공개 사용자 메시지와 별도로 운영 진단용 최소 상태만 제공한다.
- metric으로 DB pool 사용량, checkout timeout, disconnect, retry, 503 수를 수집한다.

### P1 — 계층 분리와 디자인 패턴

#### 2.10 Repository가 GraphQL 타입에 의존

`api/repositories/base.py`, `user.py`, `message.py`가 `api.graphql.fields.ResponseSchema`와 `MessageSchema`를 import한다. infrastructure가 presentation을 참조하는 역방향 의존이다. REST도 GraphQL 응답 wrapper를 간접 사용한다.

개선:

- repository interface는 entity/DTO 또는 collection을 반환하고, 실패는 application exception으로 표현한다.
- `ResponseSchema`는 제거하거나 GraphQL presentation 내부에서만 사용한다.
- `UserRepository` protocol/interface는 application 계층에, `SqlAlchemyUserRepository` 구현은 infrastructure에 둔다.
- 메모리 메시지 저장소도 같은 `MessageRepository` interface의 adapter로 구현한다.

적용 패턴: **Repository + Dependency Inversion**.

#### 2.11 업무 로직이 router와 resolver에 중복

REST와 GraphQL이 각각 password hash, repository 호출, 오류 변환, publish를 수행한다. 이미 GraphQL 사용자 생성 이중 해시 버그가 이 중복에서 발생했다.

개선:

- `UserService.create_user`, `authenticate`, `get_user`, `update_user`, `delete_user` use case를 둔다.
- controller/resolver는 입력 DTO 생성 → service 호출 → 출력 매핑만 수행한다.
- 사용자 생성 후 broadcast는 service 내부 직접 호출보다 transaction commit 이후 application event를 발행하는 방식이 안전하다.

적용 패턴: **Application Service / Use Case + Domain Event**.

#### 2.12 Transaction 경계가 repository 메서드마다 분산

각 repository 메서드가 session을 열고 commit한다. 한 use case에서 여러 repository와 event 발행을 원자적으로 조정하기 어렵고, DB commit은 성공했는데 broadcast가 실패하는 불일치가 생길 수 있다.

개선:

- request/use-case 단위 `UnitOfWork`가 session과 commit/rollback을 관리한다.
- repository는 전달받은 session을 사용하고 임의로 commit하지 않는다.
- commit 후 event publish가 반드시 보장돼야 하면 transactional outbox를 검토한다.

적용 패턴: **Unit of Work**, 필요 시 **Transactional Outbox**.

#### 2.13 전역 broadcast와 lifecycle 관리

`api/routers/graphql.py`의 module-level `broadcast`와 lazy connect는 동시 최초 요청 시 race가 가능하며 disconnect가 없다.

개선:

- FastAPI lifespan에서 broadcaster를 한 번 connect/disconnect한다.
- app state 또는 DI singleton provider로 주입한다.
- context factory는 이미 준비된 dependency를 받아 request별 context만 만든다.
- 운영에서 `memory://`는 단일 프로세스에서만 동작하므로 다중 worker/instance 구독에는 Redis 등 외부 broker adapter가 필요하다.

적용 패턴: **Resource Lifecycle Manager + Adapter**.

## 3. 추가 코드 품질 개선 사항

### Repository/SQLAlchemy

- SQLAlchemy 2.x 스타일인 `session.get(Model, id)`와 `select()` 사용을 준비한다. 현재 `query().get()`은 legacy API다.
- `update()`에서 `entries.first()`를 세 번 호출해 불필요한 query가 발생한다. entity를 한 번 조회해 수정하고 refresh한다.
- `RepositoryBase`의 오류 메시지가 모든 model에 대해 `User with id...`라고 고정되어 있다.
- `get_by_username()`의 `like()`는 wildcard 동작을 허용한다. 정확한 로그인 식별자는 `==`를 사용한다.
- `IntegrityError` 메시지에 `item.json()`을 넣으면 password가 로그/응답에 노출될 수 있다.
- `logging.info()` 대신 module logger와 구조화된 context를 사용한다.
- `scoped_session`이 필요한 실행 모델인지 검토한다. FastAPI request dependency로 명시적인 session을 제공하면 lifecycle이 더 분명하다.

### REST router

- `create_user`, `update_user`가 입력 Pydantic 객체의 password를 직접 변경한다. immutable input으로 받고 service용 command를 새로 만든다.
- delete endpoint가 `204 No Content`인데 data를 반환한다. 204면 body 없이 반환하거나 200으로 바꾼다.
- endpoint 이름과 URL을 REST 관례에 맞춰 `/users`, `/users/{user_id}`로 정리할 수 있다.
- sync DB 작업을 `def` endpoint에서 실행하는 현재 방식은 FastAPI threadpool을 사용하므로 일관적이다. 향후 async SQLAlchemy로 전환하지 않는 한 resolver의 `async def` 안에서 sync DB를 직접 호출하면 event loop를 막을 수 있으므로 threadpool/service adapter를 사용한다.

### GraphQL

- resolver에서 FastAPI `HTTPException`을 사용하지 않는다. GraphQL 오류 mapper를 둔다.
- `get_user()`와 `get_users()`가 repository 실패 여부를 확인하지 않고 `.data`만 반환한다.
- `Info`에 `CustomContext` 타입 parameter를 지정해 repository/broadcast 접근을 정적으로 검사한다.
- query의 인증 permission이 주석 처리되어 있다. 사용자/비밀번호 노출 수정과 함께 접근 정책을 명확히 한다.
- file upload mutation 중 일부만 인증되어 있다. `read_files`, `read_folder`에도 동일 정책이 필요한지 결정한다.
- 업로드 크기, 파일 수, UTF-8 decode 실패를 제한/처리한다.
- `print()`와 resolver 내부 logger 설정을 제거하고 앱 공통 logging 설정을 사용한다.

### 파일 처리

- 상대 경로 `asset`은 실행 디렉터리에 따라 바뀐다. 설정에서 절대 base directory를 주입한다.
- 업로드 디렉터리 존재 확인, 크기 제한, 허용 확장자/MIME, 안전한 파일명, 디스크 오류 처리가 필요하다.
- `download_zip()`은 전체 ZIP을 메모리에 만든다. 큰 파일은 임시 파일/streaming 또는 사전 생성 artifact를 사용한다.
- 파일이 없을 때 명시적인 404, 저장소 장애 시 503/507 등 정책을 정의한다.

### 모델과 타입

- `Optional[str]` 필드의 default가 `None`이면 타입에도 `str | None`을 정확히 반영한다.
- GraphQL `ResponseSchema.data: Any`는 schema 안정성과 타입 안전성을 해친다.
- 사용하지 않는 import(`time`, 일부 model/schema import)를 제거한다.
- `MessageRepository`의 module-level mutable dict는 thread/process safe하지 않고 인스턴스 간 상태를 공유한다. lock을 사용하거나 외부 저장소 adapter로 교체한다.

## 4. 권장 목표 구조

과도한 디렉터리 세분화를 피하면서 다음 정도로 시작할 수 있다.

```text
api/
  presentation/
    rest/
      users.py
      auth.py
      health.py
      error_handlers.py
    graphql/
      schema.py
      resolvers.py
      types.py
      error_mapper.py
      context.py
  application/
    users/
      service.py
      commands.py
      ports.py
    errors.py
  domain/
    user.py
    events.py
  infrastructure/
    database.py
    unit_of_work.py
    repositories/
      sqlalchemy_users.py
      memory_messages.py
    broadcaster.py
  config.py
  container.py
```

의존 방향:

```text
REST / GraphQL
      ↓
Application Service → Repository/UnitOfWork Port
      ↓                         ↑
    Domain              SQLAlchemy Adapter
```

presentation과 infrastructure는 application이 선언한 port에 의존하고, application/domain은 FastAPI, Strawberry, SQLAlchemy를 import하지 않는다.

## 5. DB 장애 처리 흐름 제안

```text
DB driver / SQLAlchemy exception
        ↓
SqlAlchemy adapter가 rollback 및 로그 기록
        ↓
DatabaseUnavailableError(retryable, cause)
        ↓
Application service는 업무 상태를 보존하고 필요 시 제한적 재시도
        ↓
REST exception handler ──→ HTTP 503 Problem Details + Retry-After
GraphQL error mapper   ──→ errors[].extensions.code/retryable/request_id
        ↓
사용자는 안전한 안내를 받고 운영자는 request_id로 원인 추적
```

장애 유형별 권장 응답:

| 상황 | 내부 분류 | REST | GraphQL code | 사용자 행동 |
| --- | --- | --- | --- | --- |
| DB 연결 거부/단절 | `DatabaseUnavailableError` | 503 | `DATABASE_UNAVAILABLE` | 잠시 후 backoff 재시도 |
| connection pool 고갈 | `DatabaseUnavailableError` | 503 | `DATABASE_UNAVAILABLE` | 잠시 후 재시도 |
| unique 충돌 | `ConflictError` | 409 | `CONFLICT` | 입력 변경 |
| 사용자 없음 | `ResourceNotFoundError` | 404 | `NOT_FOUND` | 식별자 확인 |
| 잘못된 query/data | 내부 결함 또는 validation | 400/500 구분 | `BAD_USER_INPUT`/`INTERNAL_SERVER_ERROR` | 입력 수정 또는 문의 |

## 6. 단계별 실행 계획

### 1단계 — 안전 문제와 버그 수정

1. password를 모든 출력 schema에서 제거한다.
2. GraphQL 이중 hash를 수정하고 hash를 service 한 곳으로 이동한다.
3. `/get_user/{id}`를 `/users/{user_id}` 또는 최소 `/{user_id}`로 수정한다.
4. login 실패를 401로 통일하고 Bearer parsing/UTC 만료 검증을 테스트한다.
5. upload 인증 정책과 제한을 통일한다.

완료 조건: password가 SDL/OpenAPI/응답에 없고 인증 및 사용자 CRUD 회귀 테스트가 통과한다.

### 2단계 — 오류 계약과 DB 복원력

1. `application/errors.py`에 오류 taxonomy를 정의한다.
2. SQLAlchemy 예외 translator를 구현한다.
3. REST exception handler와 GraphQL error mapper를 추가한다.
4. `request_id` middleware와 구조화 logging을 추가한다.
5. engine에 `pool_pre_ping`, timeout을 설정한다.
6. `/health/live`, `/health/ready`를 추가한다.
7. DB down, pool timeout, reconnect 테스트를 작성한다.

완료 조건: DB를 중단해도 프로세스가 유지되고 REST는 안전한 503, GraphQL은 안정된 error code를 반환하며 readiness는 503이다.

### 3단계 — Service와 Repository 경계 분리

1. `UserService`와 repository port를 추가한다.
2. repository에서 GraphQL `ResponseSchema` 의존을 제거한다.
3. REST와 GraphQL을 같은 service에 연결한다.
4. Unit of Work로 transaction 경계를 이동한다.
5. commit 이후 event publish 정책을 정하고 필요 시 outbox를 적용한다.

완료 조건: application/domain이 FastAPI, Strawberry, SQLAlchemy를 import하지 않고 REST/GraphQL 테스트가 같은 fake service를 재사용한다.

### 4단계 — Lifecycle과 운영성

1. `create_all()`을 앱 import에서 제거하고 Alembic migration으로 대체한다.
2. DB engine/session과 broadcaster를 lifespan에서 시작/종료한다.
3. 다중 worker가 필요하면 memory broadcaster를 외부 broker로 교체한다.
4. metric, tracing, alert를 추가한다.

완료 조건: 시작/종료 시 resource leak가 없고 rolling deployment와 일시적 DB 장애 후 자동 복구가 검증된다.

## 7. 권장 테스트 목록

- service 단위 테스트: 생성, 중복, 조회 실패, password 단일 hash
- repository 통합 테스트: commit, rollback, unique conflict, session close
- DB 장애 테스트: 연결 거부, 실행 중 disconnect, pool timeout, 복구 후 정상 요청
- REST contract 테스트: 404/409/503 Problem Details, `Retry-After`, request ID
- GraphQL contract 테스트: `extensions.code`, retryable, 내부 메시지 비노출
- readiness/liveness 테스트: DB up/down 조합
- 인증 테스트: 만료, 잘못된 scheme/signature, secret 누락
- subscription 테스트: broker connect/disconnect, publish 실패, 다중 subscriber
- 파일 테스트: 미존재, 크기 초과, decode 실패, 안전한 경로

## 8. 제안하는 첫 구현 범위

첫 PR은 범위를 다음으로 제한하는 것이 안전하다.

1. password 출력 제거, 이중 hash 및 path parameter 수정
2. application exception 세 종류 추가
3. DB exception translation과 REST/GraphQL 공개 오류 mapping
4. `pool_pre_ping`과 timeout 설정
5. live/ready endpoint 및 DB down contract test

Service/Unit of Work 전체 이동은 그 다음 PR로 분리한다. 이렇게 하면 사용자에게 보이는 장애 처리부터 개선하면서, 아키텍처 이동으로 인한 회귀 범위를 통제할 수 있다.

## 9. 1차 리팩터링 적용 상태

2026-08-02 기준 다음 항목을 구현했다.

- password 출력 schema 제거 및 GraphQL 이중 hash 수정
- REST 사용자 조회 path parameter 수정과 로그인 실패 401 통일
- `ApplicationError`, `ConflictError`, `ResourceNotFoundError`, `DatabaseUnavailableError` 기반 마련
- SQLAlchemy 연결 오류를 `DatabaseUnavailableError`로 변환
- REST 503 Problem Details와 GraphQL error extensions 계약 구현
- request ID middleware 및 응답 header 추가
- DB `pool_pre_ping`, recycle/timeout 설정
- `/health/live`, `/health/ready` 추가
- 시작 시 schema 생성을 lifespan으로 이동하고 DB 장애 시 degraded 기동
- 공개 사용자 event에서 password 제거
- DB 장애·오류 계약·비밀번호 보안 회귀 테스트 추가

### 2차 적용 상태

사용자 기능에 다음 구조를 추가 적용했다.

- REST와 GraphQL이 공유하는 `UserService`
- application 계층의 `UserRepositoryPort`, `UserUnitOfWorkPort`
- transaction commit/rollback을 조정하는 `SqlAlchemyUnitOfWork`
- session만 사용하는 SQLAlchemy `UserRepository`
- application service가 단독으로 수행하는 password hash와 인증
- `ResourceNotFoundError`, `ConflictError`의 REST/GraphQL 공통 매핑
- SQLite 통합 테스트를 통한 commit, conflict rollback, 조회 실패 검증

이에 따라 사용자 repository는 GraphQL `ResponseSchema`에 더 이상 의존하지 않고 presentation 계층에서 직접 호출되지 않는다.

### 3차 적용 상태

- framework 독립적인 `Message` domain model 추가
- `MessageRepositoryPort`와 `MessageService` 추가
- in-memory message repository의 GraphQL 타입 의존 및 module 전역 상태 제거
- repository 인스턴스 상태와 lock을 사용해 기본 thread safety 확보
- REST/GraphQL context가 repository 대신 service에 의존
- broadcaster를 DI singleton으로 등록
- FastAPI lifespan에서 broadcaster connect/disconnect 보장
- message 동작과 resource lifecycle 회귀 테스트 추가

아직 남은 주요 작업은 SQLAlchemy entity와 domain model의 완전한 분리, 운영용 외부 message broker 도입, broker 장애의 공개 오류 계약, transactional outbox 검토다.

### 4차 적용 상태

- immutable `User` domain model과 SQLAlchemy `UserRecord` 분리
- repository 내부 ORM ↔ domain mapping 추가
- application port/service에서 SQLAlchemy model import 제거
- `BROADCAST_URL` 설정으로 memory/Redis backend 선택
- Redis extra와 client 의존성 추가
- 구조화 payload의 JSON 직렬화/역직렬화 adapter 추가
- `BrokerUnavailableError`와 REST 503/GraphQL extensions 오류 계약 추가
- broker 상태를 readiness에 포함
- broker 장애 후 이미 저장된 mutation에는 `operation_committed=true`, `retryable=false` 제공
- memory payload round-trip, 연결 실패, domain mapping 회귀 테스트 추가

`memory://`는 단일 프로세스 개발/테스트 전용이다. 다중 worker 또는 여러 인스턴스에서는 `.env.example` 안내에 따라 Redis URL을 설정해야 한다.

Transactional outbox는 이번 단계에서 구현하지 않았다. 현재 이벤트는 실시간 알림이며 source of truth는 DB/API 응답이다. Broker 장애 시 API가 `operation_committed`를 명시해 클라이언트의 중복 재시도를 방지한다. 이벤트의 반드시 한 번 이상 전달이 업무 요구사항이 되면 다음을 별도 변경으로 진행한다.

1. outbox table Alembic migration
2. 사용자 변경과 outbox insert의 동일 transaction 처리
3. 별도 dispatcher worker와 retry/backoff
4. event ID 기반 consumer deduplication
5. 처리 완료/실패 metric과 dead-letter 운영 정책

이는 DB schema, background worker, 전달 보장 및 중복 처리 정책을 함께 바꾸므로 단순 refactor와 분리해야 한다.
