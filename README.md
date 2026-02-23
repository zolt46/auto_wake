# AutoWake

AutoWake는 Windows 기반 공용 PC(도서관·열람실·키오스크) 환경에서 **지정 웹페이지 자동 실행**, **유휴 시 세이버 표시**, **안내 팝업 노출**, **유튜브 오디오 재생 유지**를 통합 관리하는 PySide6 데스크톱 앱입니다.

이 저장소는 현재 핵심 실행 파일(`ensure_link.py`)과 PyInstaller 스펙(`autowake_beta.spec`) 중심의 단일-스크립트 구조입니다.

## 빠른 문서 안내

- 개발자/아키텍처 문서: [`docs/developer-guide.md`](docs/developer-guide.md)
- EXE 패키징 문서: [`docs/packaging-guide.md`](docs/packaging-guide.md)
- 운영자/사용자 메뉴얼: [`docs/user-manual.md`](docs/user-manual.md)

---

## 구현된 기능 요약

- 다중 워커 분리 실행
  - UI(`--mode ui`), Audio(`--mode audio`), Target+Notice(`--mode target`), Saver(`--mode saver`) 프로세스를 분리하여 안정성 확보.
- Chrome 자동 실행/복구
  - 대상 URL 리스트를 지정한 프로필로 실행하고, 종료/창 유실 시 쿨다운 정책에 따라 재실행.
- 오디오 재생 유지
  - YouTube URL(리스트) 재생을 Chrome 또는 PWA 모드로 실행 가능.
- 유휴 감지 세이버
  - WinAPI 입력 유휴 시간 기반으로 세이버를 표시/해제.
- 안내 팝업(Notice)
  - 제목/본문/푸터/폰트/정렬/이미지/윈도우 크기 프리셋/반복 표시 등 상세 설정.
- 트레이 기반 백그라운드 운영
  - 앱 창을 숨겨도 트레이에서 시작/중지/설정/종료 제어.
- 설정 영속화
  - `C:\AutoWake\config.json`, `notice_state.json`, `autowake.log` 기반 상태/로그 관리.

---

## 저장소 구조

```text
auto_wake/
├─ ensure_link.py          # 메인 애플리케이션(모든 UI/워커/설정/런처 로직)
├─ autowake_beta.spec      # PyInstaller 빌드 스펙
├─ README.md               # 프로젝트 개요(본 문서)
└─ docs/
   ├─ developer-guide.md   # 개발자 문서(구조/클래스/동작 상세)
   ├─ packaging-guide.md   # exe 패키징 절차/산출물/배포 체크리스트
   └─ user-manual.md       # 운영자/사용자 메뉴얼
```

---

## 빠른 시작(개발 실행)

> Windows + Python 3.11 권장

```bash
python -m venv .venv
.venv\Scripts\activate
pip install pyside6 pyinstaller pillow
python ensure_link.py
```

앱이 켜지면 설정 저장 후 내부적으로 워커 프로세스를 자동 기동합니다.

---

## 기본 실행/운영 경로

- 기본 작업 디렉터리: `C:\AutoWake`
- 설정 파일: `C:\AutoWake\config.json`
- 런타임 상태: `C:\AutoWake\notice_state.json`
- 로그 파일: `C:\AutoWake\autowake.log`
- Chrome 프로필(워커별): `C:\AutoWake\chrome_profiles\{audio|target}`

---

## EXE 패키징

PyInstaller 스펙 기반으로 빌드합니다.

```bash
pyinstaller autowake_beta.spec
```

상세 옵션·아이콘·assets 포함 정책은 `docs/packaging-guide.md`를 참고하세요.

---

## 운영 시 참고

- 공용 PC 운영 정책(전체화면/F11/Alt+F4 안내)은 Notice 영역에 기본 탑재되어 있습니다.
- 종료/재실행 동작은 오디오/대상 워커별 `repeat/once`, 시작 지연, 재실행 쿨다운 설정에 크게 영향을 받습니다.
- 초기 암호 정책과 변경 흐름은 사용자 메뉴얼의 "관리자 비밀번호" 절을 참고하세요.
