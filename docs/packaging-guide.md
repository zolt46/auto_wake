# AutoWake EXE 패키징 가이드

## 1. 대상/전제

이 문서는 `ensure_link.py`를 Windows 실행 파일(`autowake_beta.exe`)로 빌드해 배포하는 절차를 설명합니다.

전제:
- OS: Windows 10/11
- Python: 3.11 권장
- 의존성: PySide6, PyInstaller, Pillow(ico 자동생성용)

---

## 2. 빌드 입력 파일

- 엔트리 코드: `ensure_link.py`
- 스펙 파일: `autowake_beta.spec`
- 리소스: `assets/default_saver.png`, `assets/notice_default_1.png`, `assets/notice_default_2.png`, `assets/icon.png`, `assets/logo.png`

`autowake_beta.spec`는 아이콘 처리 로직을 포함합니다.

- `assets/icon.ico`가 있으면 사용
- 없고 `assets/icon.png`가 있으면 Pillow로 `.ico` 생성 시도
- Pillow 없거나 변환 실패 시 PNG를 대체 사용

---

## 3. 빌드 절차(권장)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install pyside6 pyinstaller pillow
pyinstaller autowake_beta.spec
```

### 산출물

기본적으로 아래 폴더가 생성됩니다.

```text
build/
  autowake_beta/
dist/
  autowake_beta.exe
```

단일 파일(onefile) 여부는 spec 설정에 따릅니다. 현재 spec은 `EXE(...)` 형태로 작성되어 단일 실행 파일 배포 형태를 지향합니다.

---

## 4. 배포 파일 구성

최소 배포:

- `autowake_beta.exe`

권장 동봉:

- 설치/운영 가이드 문서(`README.md`, `docs/user-manual.md`)
- 기본 `config.json` 템플릿(선택)

런타임에 `C:\AutoWake` 경로가 자동 생성되며, 설정/로그/상태가 해당 경로에 쌓입니다.

---

## 5. EXE 실행 방식

UI 실행:

```bash
autowake_beta.exe
```

워커 직접 실행(디버깅 용도):

```bash
autowake_beta.exe --mode audio
autowake_beta.exe --mode target
autowake_beta.exe --mode saver
```

운영에서는 UI만 실행하면 내부적으로 워커를 자동 시작/동기화합니다.

---

## 6. 패키징 시 자주 발생하는 이슈

### 6.1 아이콘 미적용
- 원인: `assets/icon.png` 누락, Pillow 미설치
- 조치: `assets/icon.ico`를 직접 제공하거나 Pillow 설치 후 재빌드

### 6.2 리소스 이미지 표시 실패
- 원인: spec `datas` 누락/경로 오타
- 조치: spec 내 `datas=[(...)]` 경로를 실제 경로와 일치시킴

### 6.3 실행은 되지만 Chrome 제어 실패
- 원인: 대상 PC에 Chrome 미설치/기업 정책 제한
- 조치: Chrome 설치 확인, 보안 정책 예외 검토

### 6.4 PWA 모드 불안정
- 원인: 사용자 프로필별 PWA 설치 상태 불일치
- 조치: 오디오 실행 모드를 Chrome으로 전환하여 서비스 지속

---

## 7. 배포 전 체크리스트

- [ ] 깨끗한 가상환경에서 빌드 성공
- [ ] 실행 파일 서명(조직 정책이 있으면 필수)
- [ ] 대상 PC에서 최초 실행 시 `C:\AutoWake` 생성 확인
- [ ] 설정 저장/재시작 후 설정 유지 확인
- [ ] 워커 자동 재실행 동작 확인(오디오/대상)
- [ ] 장시간 운용 테스트(화면보호기/Notice 충돌 여부)

