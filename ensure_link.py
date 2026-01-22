import ctypes
from ctypes import wintypes
import os
import subprocess
import time
from datetime import datetime
import sys
import tkinter as tk
from PIL import Image, ImageTk

# ================== 설정 ==================
URL_FULLSCREEN = "https://lib.koreatech.ac.kr/search/i-discovery"
LOCAL_IMAGE = r"C:\Users\seewo\Desktop\closing_new_proj\auto_close\AutoWake\학술정보팀) 협정PC 안내 바탕화면.png"

WORK_DIR = r"C:\AutoWake"

# idle 기준(초): 이 시간 이상 입력 없으면 이미지 세이버 표시
IDLE_TO_SHOW_SEC = 10

# active 기준(초): 입력 감지되면 즉시 세이버 숨김
ACTIVE_THRESHOLD_SEC = 1

# 루프 주기(초)
POLL_SEC = 0.5

# 크롬이 꺼졌을 때 재실행 쿨다운(초) - 너무 자주 뜨는 것 방지
CHROME_RELAUNCH_COOLDOWN_SEC = 10

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
# ==========================================


# ---------- 내부 중복 실행 방지(뮤텍스) ----------
def single_instance_or_exit(name="AutoWake_EnsureLink_SingleInstance"):
    """
    같은 PC에서 이 프로그램이 이미 실행 중이면 즉시 종료.
    (작업 스케줄러/시작프로그램/수동 실행 등 어떤 경우에도 안전)
    """
    kernel32 = ctypes.windll.kernel32
    CreateMutexW = kernel32.CreateMutexW
    GetLastError = kernel32.GetLastError

    mutex = CreateMutexW(None, False, name)
    ERROR_ALREADY_EXISTS = 183
    if GetLastError() == ERROR_ALREADY_EXISTS:
        raise SystemExit("Already running")
    return mutex  # 프로세스가 살아있는 동안 유지


# ----- WinAPI(Idle 체크) -----
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GetLastInputInfo = user32.GetLastInputInfo
GetTickCount64 = kernel32.GetTickCount64


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def log(msg: str):
    os.makedirs(WORK_DIR, exist_ok=True)
    p = os.path.join(WORK_DIR, "autowake.log")
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")


def seconds_since_last_input() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    elapsed_ms = int(GetTickCount64()) - int(info.dwTime)
    return elapsed_ms / 1000.0


def find_chrome_exe() -> str:
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return "chrome"


def launch_fullscreen_site() -> subprocess.Popen | None:
    """
    크롬 FULL(사이트) 실행 후 Popen 리턴.
    실패하면 None.
    """
    chrome = find_chrome_exe()
    profile_dir = os.path.join(WORK_DIR, "ChromeProfile_FULL")
    os.makedirs(profile_dir, exist_ok=True)

    args = [
        chrome,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "--start-fullscreen",
        URL_FULLSCREEN,
    ]
    try:
        log(f"Launching FULL: {args}")
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"ERROR launching FULL: {e}")
        return None


# ----- 세이버 오버레이(Tkinter) -----
class OverlaySaver:
    def __init__(self, image_path: str):
        self.image_path = image_path
        self.root = None
        self.visible = False
        self.tk_img = None

    def show(self):
        if self.visible:
            return
        if not os.path.exists(self.image_path):
            log(f"LOCAL_IMAGE not found: {self.image_path}")
            return

        self.root = tk.Tk()

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # Windows10 안정: fullscreen 속성 대신 geometry로 전체 덮기
        self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.overrideredirect(True)   # 테두리/작업표시줄 없이
        self.root.attributes("-topmost", True)

        canvas = tk.Canvas(self.root, width=sw, height=sh, highlightthickness=0, bg="black")
        canvas.pack(fill="both", expand=True)

        img = Image.open(self.image_path)
        img = self.fit_contain(img, sw, sh)
        self.tk_img = ImageTk.PhotoImage(img)
        canvas.create_image(sw // 2, sh // 2, image=self.tk_img)

        self.visible = True
        log("Overlay SHOW")
        self.root.update()

    def hide(self):
        if not self.visible:
            return
        try:
            self.root.destroy()
        except Exception:
            pass
        self.root = None
        self.visible = False
        self.tk_img = None
        log("Overlay HIDE")

    def pump(self):
        """표시 중일 때 화면 갱신 유지"""
        if self.visible and self.root:
            try:
                self.root.update()
            except Exception:
                self.visible = False
                self.root = None
                self.tk_img = None

    @staticmethod
    def fit_contain(img: Image.Image, w: int, h: int) -> Image.Image:
        iw, ih = img.size
        scale = min(w / iw, h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        return img.resize((nw, nh), Image.LANCZOS)


def main():
    # 0) 단일 실행 보장
    _mutex = single_instance_or_exit()

    os.makedirs(WORK_DIR, exist_ok=True)
    log("===== START =====")

    # 1) 크롬 FULL 실행(1회) + 감시 핸들 저장
    full_proc = launch_fullscreen_site()
    last_full_launch_ts = time.time()

    saver = OverlaySaver(LOCAL_IMAGE)

    while True:
        # 2) 크롬이 죽었으면 자동 재실행(쿨다운)
        if full_proc is None or full_proc.poll() is not None:
            now = time.time()
            if now - last_full_launch_ts >= CHROME_RELAUNCH_COOLDOWN_SEC:
                log("FULL chrome not running -> relaunch")
                full_proc = launch_fullscreen_site()
                last_full_launch_ts = now

        # 3) 세이버 로직(크롬과 무관하게 동작)
        idle = seconds_since_last_input()

        if idle <= ACTIVE_THRESHOLD_SEC:
            saver.hide()
        elif idle >= IDLE_TO_SHOW_SEC:
            saver.show()

        saver.pump()
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        # 이미 실행 중이면 조용히 종료
        sys.exit(0)
    except Exception as e:
        # 예외 로그 남기고 종료
        try:
            log(f"FATAL: {e}")
        except Exception:
            pass
        sys.exit(1)
