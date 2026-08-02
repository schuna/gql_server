# 중복 생성 요청을 기존 엔트리 반환 방식으로 변경하는 방안 검토

## 결론

`CreateUser`를 단순히 `ConflictError` 대신 기존 `User`를 반환하도록 바꾸는 것은 가능하다. 다만 모든 unique-key 충돌을 성공으로 취급하면 요청과 다른 사용자를 반환할 수 있으므로, **username과 email이 모두 동일한 한 사용자와 매칭될 때만 멱등 성공으로 처리**하고, 부분 충돌이나 교차 충돌은 기존처럼 `ConflictError`로 유지하는 방식을 권장한다.

또한 중복 요청에서는 `add_user` 이벤트를 다시 발행하지 않아야 한다. 따라서 서비스가 `User`만 반환해서는 resolver가 신규 생성과 기존 엔트리 반환을 구분할 수 없으며, 생성 여부를 함께 반환하는 결과 타입이 필요하다.

## 현재 동작

호출 흐름은 다음과 같다.

1. GraphQL `create_user` resolver가 `UserService.create()`를 호출한다.
2. `UserService.create()`가 비밀번호를 해시하고 `UserRepository.add()`를 호출한다.
3. repository의 `session.flush()` 또는 unit of work의 `session.commit()`에서 unique 제약 위반이 발생한다.
4. `IntegrityError`가 `api.errors.ConflictError("Resource already exists")`로 변환된다.
5. GraphQL resolver가 이를 GraphQL conflict error로 다시 변환한다.

`users` 테이블에는 `username`, `email` 각각에 unique 제약이 있다. 현재 `ConflictError`에는 어느 필드가 충돌했는지 또는 충돌한 기존 사용자 식별자가 포함되지 않는다.

REST의 `POST /create_user`도 같은 `UserService.create()`를 사용하므로 서비스 동작을 변경하면 GraphQL뿐 아니라 REST API에도 동일하게 적용된다.

## 권장 의미 규칙

요청 `(username, email)`과 DB 상태를 비교하여 다음처럼 처리한다.

| DB 매칭 상태 | 권장 결과 | 이유 |
|---|---|---|
| username/email 모두 매칭 없음 | 새 사용자 생성 | 정상 생성 |
| 두 값이 동일한 기존 사용자 한 명과 매칭 | 기존 사용자 반환, `created=false` | 동일 생성 요청의 안전한 재시도 |
| username만 기존 사용자와 매칭 | `ConflictError` | 요청 email과 다른 사용자를 성공으로 반환하면 입력 오류를 숨김 |
| email만 기존 사용자와 매칭 | `ConflictError` | 요청 username과 다른 사용자를 성공으로 반환하면 계정 열거 및 오인 가능 |
| username과 email이 서로 다른 두 사용자와 매칭 | `ConflictError` | 반환할 엔트리가 하나로 결정되지 않음 |

비밀번호는 동일성 판정에 사용하지 않는 것이 적절하다. 일반적인 password hash는 salt 때문에 같은 평문도 hash가 달라질 수 있고, 중복 생성 요청이 기존 계정의 비밀번호를 검증하거나 갱신하는 효과를 가져서도 안 된다. 기존 사용자를 반환할 때 GraphQL/REST 응답에는 현재처럼 password를 노출하지 않는다.

만약 제품 요구사항이 "username 또는 email 중 하나만 같아도 무조건 기존 엔트리 반환"이라면, 어느 키를 우선할지와 두 키가 서로 다른 사용자를 가리킬 때의 규칙을 먼저 확정해야 한다. 보안과 예측 가능성 측면에서는 권장하지 않는다.

## 권장 설계

### 1. 생성 결과에 신규 생성 여부 포함

application 계층에 다음과 같은 결과 타입을 둔다.

```python
@dataclass(frozen=True)
class CreateUserResult:
    user: User
    created: bool
```

예를 들어 `UserService.create_or_get(item) -> CreateUserResult`로 명시하거나 기존 `create()`의 반환 타입을 이 결과로 변경할 수 있다. 기존 `create()`를 변경하면 GraphQL resolver와 REST router를 함께 수정해야 하므로, 호환성을 중시하면 새 메서드를 추가하고 모든 생성 진입점을 점진적으로 전환하는 편이 안전하다.

외부 GraphQL 스키마의 반환 타입은 계속 `UserSchema`로 유지할 수 있어 클라이언트 계약 변경은 필수가 아니다. 다만 클라이언트가 신규 생성 여부를 알아야 한다면 별도의 GraphQL payload(`user`, `created`)로 확장하는 것은 별도 버전/API 변경으로 다루는 것이 좋다.

### 2. repository 조회 기능 추가

`UserRepositoryPort`와 구현체에 email 조회 또는 두 unique 필드를 한 번에 조회하는 기능을 추가한다. 한 번의 OR 조회 결과를 사용하면 username/email이 동일 사용자에 매칭되는지, 서로 다른 사용자에 매칭되는지를 명확히 판정할 수 있다.

권장 예시는 `find_by_username_or_email(username, email) -> list[User]`이다. "없음"은 정상 조회 결과이므로 이 메서드는 `ResourceNotFoundError` 대신 빈 목록을 반환하는 편이 판정 로직을 단순하게 한다.

### 3. 사전 조회와 DB 제약을 함께 사용

사전 조회만으로는 동시 요청 race condition을 막을 수 없다. 다음 두 경로가 모두 필요하다.

1. 생성 전에 기존 unique 값들을 조회하여 일반적인 중복 요청을 판정한다.
2. 조회 직후 다른 트랜잭션이 삽입할 수 있으므로, `flush/commit`의 `IntegrityError`도 처리한다.

race에서 충돌하면 실패한 session은 반드시 rollback/종료한 뒤 **새 unit of work/session에서 다시 조회**해야 한다. 현재 `Database.session()` context manager는 예외 시 rollback하므로, `ConflictError`를 unit of work 바깥에서 잡은 후 새 unit of work로 재조회하는 구조가 안전하다. 실패 상태인 동일 session에서 즉시 SELECT를 시도하면 SQLAlchemy의 pending rollback 오류가 날 수 있다.

재조회 결과가 위의 "두 값이 동일 사용자 한 명과 매칭" 조건이면 기존 사용자와 `created=false`를 반환하고, 그렇지 않으면 `ConflictError`를 유지한다. DB connection 장애는 현재와 같이 `DatabaseUnavailableError`로 전파해야 한다.

DB 고유 제약은 제거하지 않는다. application의 조회는 UX/멱등 응답을 위한 것이고, 최종 데이터 무결성은 DB 제약이 보장해야 한다.

### 4. 이벤트는 신규 생성 시에만 발행

현재 GraphQL resolver는 서비스 호출이 성공하면 항상 `add_user`를 publish한다. 기존 엔트리를 반환하는 중복 요청에서도 이를 그대로 실행하면 subscription 소비자는 동일 사용자를 새로 추가된 것으로 오해한다.

따라서 `CreateUserResult.created is True`일 때만 이벤트를 발행한다. `created=false`이면 저장과 publish를 모두 생략하고 기존 public user를 즉시 반환한다. 신규 생성 후 broker publish 실패 시 사용하는 `operation_committed=true` 동작은 그대로 유지한다.

REST 생성 엔드포인트에는 이벤트 발행이 없으므로 결과의 `user`만 응답 모델에 반환하면 된다. HTTP 상태를 현재처럼 200으로 유지할지, 신규 생성만 201로 바꿀지는 별도 API 정책이지만 중복 반환과 직접 관련된 필수 변경은 아니다.

## 수정 대상

- `api/application/user_service.py`: create-or-get 정책, race 후 재조회, `CreateUserResult` 반환
- `api/application/ports.py`: unique 필드 조회 port 추가
- `api/repositories/user.py`: username/email 동시 조회 구현
- `api/graphql/resolvers.py`: conflict 변환은 부분/교차 충돌에만 유지하고, `created=true`일 때만 이벤트 publish
- `api/routers/login.py`: 결과 객체에서 `user`를 반환하도록 조정
- 필요 시 `api/domain/` 또는 application 모듈: `CreateUserResult` 정의

현재 repository와 unit of work 양쪽 모두 `IntegrityError`를 `ConflictError`로 변환한다. 실제 insert는 repository의 `_flush()`에서 먼저 실패하므로 중복 변환 책임이 겹친다. 이번 변경에서 변환 지점을 한 계층으로 정리하면 race 처리와 테스트가 더 명확해진다. 단, update 시 unique 충돌도 계속 `ConflictError`여야 하므로 create 전용 멱등 처리와 update 충돌 처리를 혼동하면 안 된다.

## 필요한 테스트

### 서비스/repository

- 최초 요청은 사용자를 생성하고 `created=true`를 반환한다.
- 동일 username/email의 재요청은 행을 추가하지 않고 같은 id와 `created=false`를 반환한다.
- 중복 재요청의 새 password가 저장된 password를 변경하지 않는다.
- username만 같고 email이 다르면 `ConflictError`이다.
- email만 같고 username이 다르면 `ConflictError`이다.
- username과 email이 각각 다른 기존 사용자를 가리키면 `ConflictError`이다.
- 동시 생성으로 insert가 충돌한 뒤 새 session 재조회에서 동일 엔트리를 반환한다.
- race 후 재조회가 부분/교차 충돌이면 `ConflictError`이다.
- update의 unique 충돌은 기존처럼 `ConflictError`이다.

### GraphQL/REST

- GraphQL 최초 생성은 public user를 반환하고 `add_user`를 한 번 publish한다.
- GraphQL 동일 요청 재시도는 같은 user를 반환하고 publish하지 않는다.
- 부분/교차 충돌은 기존 GraphQL conflict code/extension을 유지한다.
- 신규 생성 후 broker 실패는 기존처럼 `operation_committed=true`를 반환한다.
- 중복 기존값 반환 경로에서는 broker를 호출하지 않으므로 broker 장애가 응답을 실패시키지 않는다.
- REST 최초 생성과 동일 재요청이 모두 password 없는 기존 response schema를 만족한다.

## 주의 사항

- 이 변경은 일반적인 의미의 완전한 idempotency key 구현은 아니다. 동일 `(username, email)` 요청만 멱등하게 만든다. 요청 단위의 정확한 재처리가 필요하면 별도 idempotency key 저장소가 필요하다.
- 기존 사용자 존재 여부를 응답 차이로 노출할 수 있으므로 공개 회원가입 API의 계정 열거 정책을 검토해야 한다. 현재도 conflict 응답으로 존재 여부를 어느 정도 노출하고 있지만, 기존 user의 id/username/email을 반환하면 노출 정보가 더 많아진다.
- 따라서 인증되지 않은 공개 생성 API라면 기존 엔트리 전체 반환 요구 자체를 보안 관점에서 재검토하는 것이 좋다. 요구사항을 유지한다면 최소한 현재 public schema 밖의 필드는 절대 반환하지 않아야 한다.
- application 수준의 일반 `ConflictError`를 모두 기존값 반환으로 바꾸지 말고, `CreateUser`의 명시적인 동일성 판정에만 적용해야 한다.

## 구현 순서 제안

1. 중복의 의미를 "username과 email이 동일 사용자와 모두 일치"로 확정한다.
2. repository port와 unique 조회 구현을 추가한다.
3. `CreateUserResult` 및 service의 create-or-get 로직을 추가한다.
4. GraphQL/REST 진입점을 결과 타입에 맞추고 이벤트 조건을 추가한다.
5. 정상 중복, 부분/교차 충돌, race, 이벤트 미발행 테스트를 추가한다.
6. 전체 테스트를 실행하여 기존 conflict/error contract와 인증 흐름에 회귀가 없는지 확인한다.
