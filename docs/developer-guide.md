# AutoWake 개발자 가이드

## 1. 프로젝트 목적과 실행 모델

AutoWake는 공용 Windows PC에서 다음을 자동화하도록 설계되었습니다.

1. 지정 웹사이트(도서관/검색 페이지) 자동 실행 및 유지
2. 오디오(유튜브) 재생 프로세스 분리 관리
3. 사용자 유휴 상태에서 세이버 출력
4. 정책/이용 안내 팝업 노출

핵심은 **단일 코드베이스 + 다중 실행 모드**입니다. `ensure_link.py` 하나를 `--mode` 인자로 분기해 서로 독립된 워커를 실행합니다.

- `ui`: 관리자 설정 UI + 트레이 + 워커 오케스트레이션
- `audio`: 오디오 전용 워커
- `target`: 대상 URL 브라우저 + Notice 팝업 워커
- `saver`: 유휴 감지 세이버 워커

---

## 2. 코드 구조(논리 모듈)

`ensure_link.py`는 물리적으로 단일 파일이지만, 논리적으로 아래 모듈로 구분됩니다.

### 2.1 상수/기본 정책
- 기본 URL/오디오 URL 목록
- Notice 기본 본문/푸터 텍스트
- 번들 이미지·아이콘 경로
- 버전 메타데이터

### 2.2 파일/상태 유틸
- `config_file_path`, `notice_state_path`, `worker_lock_path`
- JSON 기반 설정/상태 읽기·쓰기
- PID 기반 워커 중복 실행 잠금(`*.lock`)

### 2.3 런타임 유틸
- `log`: `autowake.log` 파일 기록
- `resource_path`: PyInstaller `_MEIPASS` 대응
- `single_instance_or_exit`: UI 단일 인스턴스 뮤텍스
- `seconds_since_last_input`: WinAPI 기반 유휴 시간

### 2.4 설정 모델
- `@dataclass AppConfig`
- `from_dict`, `load_config`, `save_config`
- 패스워드 해시/Salt 마이그레이션 지원

### 2.5 브라우저/PWA 실행 유틸
- Chrome 경로 탐색, 인자 구성
- YouTube PWA App ID 탐색
- `launch_chrome`, `launch_pwa`
- 창 핸들 탐색/최소화/복원/강제종료

### 2.6 UI 컴포넌트
- 커스텀 토글/스테퍼/카드
- 비밀번호/경고/URL 목록 다이얼로그
- Notice 미리보기/설정 다이얼로그
- 메인 설정 창 `MainWindow`

### 2.7 워커
- `AudioWorker`
- `TargetWorker`
- `SaverWorker`

### 2.8 엔트리포인트
- `run_audio_worker`, `run_target_worker`, `run_saver_worker`, `run_ui`
- `main()`에서 `--mode` 파싱 후 분기

---

## 3. 핵심 클래스 설명

## `AppConfig`
시스템 전체 정책을 보관하는 단일 설정 모델입니다.

- 실행 대상 URL/오디오 URL 목록
- 워커별 enable/repeat/start delay/cooldown
- Notice 텍스트/폰트/색/이미지/크기
- 테마/포인트 색상
- 비밀번호 해시 정보

`load_config()`는 기본 경로(`C:\AutoWake`)를 우선 사용하되, 접근 실패 시 현재 디렉터리로 폴백합니다.

## `ProcessManager`
UI가 워커 서브프로세스를 시작/중지하는 책임을 갖습니다.

- 개발 모드: `python ensure_link.py --mode ...`
- 배포 모드(frozen): `autowake_beta.exe --mode ...`

## `MainWindow`
운영자가 실제로 다루는 관리자 UI입니다.

- 탭 기반 설정(대상/오디오/세이버/안내/테마)
- AutoSave + 즉시 워커 동기화
- 트레이 아이콘/메뉴 제어
- 비밀번호 보호 설정창 진입

## `AudioWorker`
오디오 재생 정책을 수행합니다.

- Chrome/PWA 선택 실행
- repeat/once 정책
- 최소화/복원 타이밍 제어
- 재실행 쿨다운 제어

## `TargetWorker`
대상 URL 유지 + Notice 팝업 상태 조정을 수행합니다.

- 대상 브라우저 실행/복구
- 창 유실 시 재기동
- Notice 표시/잠금/해제
- Saver/UI active 상태 파일(`notice_state.json`) 기반 상호작용

## `SaverWorker`
유휴 시간이 임계값을 넘으면 세이버를 표시합니다.

- WinAPI 유휴 시간 폴링
- 사용자 입력 감지 즉시 hide
- 작업영역/전체화면 모드 지원

---

## 4. 워커 간 상태 동기화

프로세스 간 IPC 대신 파일 상태를 사용합니다.

- 상태 파일: `notice_state.json`
- 주요 키: `ui_active`, `saver_active`, `saver_trigger_at`, `notice_dismissed_at`

동작 예시:

1. Saver가 활성화되면 `saver_active=1`, `saver_trigger_at=...` 기록
2. TargetWorker가 이를 감지해 Notice 정책(재표시/잠금)을 조절
3. UI가 설정창 열림/닫힘에 따라 `ui_active` 반영

이 구조는 구현이 단순하고 장애 복원에 강하지만, 파일 I/O 기반이므로 고빈도 업데이트는 최소화되어야 합니다.

---

## 5. 설정/로그/런타임 파일

기본 경로 `C:\AutoWake` 아래:

- `config.json`: 전체 설정
- `notice_state.json`: 런타임 공유 상태
- `autowake.log`: 오류/이벤트 로그
- `audio_worker.lock`: 오디오 워커 중복 방지 잠금
- `chrome_profiles/audio`, `chrome_profiles/target`: Chrome 사용자 데이터

---

## 6. 폴더 구성 제안(리팩토링 관점)

현재 단일 파일 구조는 빠른 배포에 유리하지만, 확장성 관점에서는 아래 분리를 권장합니다.

```text
src/autowake/
├─ core/
│  ├─ config.py
│  ├─ state.py
│  ├─ logging.py
│  └─ winapi.py
├─ browser/
│  ├─ chrome.py
│  └─ pwa.py
├─ workers/
│  ├─ audio_worker.py
│  ├─ target_worker.py
│  └─ saver_worker.py
├─ ui/
│  ├─ main_window.py
│  ├─ dialogs/
│  └─ widgets/
└─ main.py
```

리팩토링 시 우선순위:
1. `AppConfig`/I/O 분리
2. 브라우저 유틸 분리
3. 워커 분리
4. UI 컴포넌트 분리

---

## 7. 개발/디버깅 팁

- 워커 단독 실행으로 범위 축소:
  - `python ensure_link.py --mode audio`
  - `python ensure_link.py --mode target`
  - `python ensure_link.py --mode saver`
- 로그 확인: `C:\AutoWake\autowake.log`
- 설정 리셋: `config.json` 백업 후 삭제
- PWA 문제 시 Chrome 모드로 강제 전환해 원인 분리

---

## 8. 품질/운영 체크리스트

- [ ] Chrome 설치 경로 탐지 확인
- [ ] 관리자 비밀번호 초기화/변경 플로우 점검
- [ ] URL/오디오 목록 비정상 입력 검증
- [ ] 작업영역 모드(태스크바 포함/제외) 실제 모니터 환경 테스트
- [ ] 장시간(8h+) soak test로 재실행 안정성 확인

