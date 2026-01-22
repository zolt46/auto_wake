import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict
import json
import os
import subprocess
import time
from datetime import datetime
import sys
import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import pystray

# ================== 설정 ==================
DEFAULT_URL = "https://lib.koreatech.ac.kr/search/i-discovery"
DEFAULT_LOCAL_IMAGE = (
    r"C:\Users\seewo\Desktop\closing_new_proj\auto_close\AutoWake"
    r"\학술정보팀) 협정PC 안내 바탕화면.png"
)

WORK_DIR = r"C:\AutoWake"
CONFIG_FILE = os.path.join(WORK_DIR, "config.json")

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


@dataclass
class AppConfig:
    url: str = DEFAULT_URL
    image_path: str = DEFAULT_LOCAL_IMAGE
    work_dir: str = WORK_DIR
    idle_to_show_sec: float = 10.0
    active_threshold_sec: float = 1.0
    poll_sec: float = 0.5
    chrome_relaunch_cooldown_sec: float = 10.0
    chrome_fullscreen: bool = True
    chrome_kiosk: bool = False
    saver_enabled: bool = True
    chrome_repeat: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        return cls(
            url=data.get("url", DEFAULT_URL),
            image_path=data.get("image_path", DEFAULT_LOCAL_IMAGE),
            work_dir=data.get("work_dir", WORK_DIR),
            idle_to_show_sec=float(data.get("idle_to_show_sec", 10.0)),
            active_threshold_sec=float(data.get("active_threshold_sec", 1.0)),
            poll_sec=float(data.get("poll_sec", 0.5)),
            chrome_relaunch_cooldown_sec=float(
                data.get("chrome_relaunch_cooldown_sec", 10.0)
            ),
            chrome_fullscreen=bool(data.get("chrome_fullscreen", True)),
            chrome_kiosk=bool(data.get("chrome_kiosk", False)),
            saver_enabled=bool(data.get("saver_enabled", True)),
            chrome_repeat=bool(data.get("chrome_repeat", True)),
        )


def load_config() -> AppConfig:
    os.makedirs(WORK_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        cfg = AppConfig()
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig.from_dict(data)
    except Exception as e:
        log(f"CONFIG load error: {e}")
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    os.makedirs(WORK_DIR, exist_ok=True)
    data = asdict(cfg)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"CONFIG save error: {e}")


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


def launch_fullscreen_site(cfg: AppConfig) -> subprocess.Popen | None:
    """
    크롬 FULL(사이트) 실행 후 Popen 리턴.
    실패하면 None.
    """
    chrome = find_chrome_exe()
    profile_dir = os.path.join(cfg.work_dir, "ChromeProfile_FULL")
    os.makedirs(profile_dir, exist_ok=True)

    args = [
        chrome,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
    ]
    if cfg.chrome_fullscreen:
        args.append("--start-fullscreen")
    if cfg.chrome_kiosk:
        args.append("--kiosk")
    args.append(cfg.url)
    try:
        log(f"Launching FULL: {args}")
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"ERROR launching FULL: {e}")
        return None


# ----- 세이버 오버레이(Tkinter) -----
class OverlaySaver:
    def __init__(self, root: tk.Tk, image_path: str):
        self.root = root
        self.image_path = image_path
        self.window = None
        self.visible = False
        self.tk_img = None

    def show(self):
        if self.visible:
            return
        if not os.path.exists(self.image_path):
            log(f"LOCAL_IMAGE not found: {self.image_path}, using fallback")
            img = self._build_fallback_image()
        else:
            img = Image.open(self.image_path)

        self.window = tk.Toplevel(self.root)

        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()

        # Windows10 안정: fullscreen 속성 대신 geometry로 전체 덮기
        self.window.geometry(f"{sw}x{sh}+0+0")
        self.window.overrideredirect(True)   # 테두리/작업표시줄 없이
        self.window.attributes("-topmost", True)

        canvas = tk.Canvas(
            self.window, width=sw, height=sh, highlightthickness=0, bg="black"
        )
        canvas.pack(fill="both", expand=True)

        img = self.fit_contain(img, sw, sh)
        self.tk_img = ImageTk.PhotoImage(img)
        canvas.create_image(sw // 2, sh // 2, image=self.tk_img)

        self.visible = True
        log("Overlay SHOW")
        self.window.update()

    def hide(self):
        if not self.visible:
            return
        try:
            self.window.destroy()
        except Exception:
            pass
        self.window = None
        self.visible = False
        self.tk_img = None
        log("Overlay HIDE")

    def pump(self):
        """표시 중일 때 화면 갱신 유지"""
        if self.visible and self.window:
            try:
                self.window.update()
            except Exception:
                self.visible = False
                self.window = None
                self.tk_img = None

    @staticmethod
    def fit_contain(img: Image.Image, w: int, h: int) -> Image.Image:
        iw, ih = img.size
        scale = min(w / iw, h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        return img.resize((nw, nh), Image.LANCZOS)

    def _build_fallback_image(self) -> Image.Image:
        w, h = 1600, 900
        img = Image.new("RGB", (w, h), (20, 24, 33))
        draw = ImageDraw.Draw(img)
        title = "AutoWake"
        subtitle = "이미지 파일을 찾을 수 없습니다."
        detail = "설정에서 경로를 확인하세요."
        try:
            title_font = ImageFont.truetype("Segoe UI", 72)
            subtitle_font = ImageFont.truetype("Segoe UI", 36)
            detail_font = ImageFont.truetype("Segoe UI", 28)
        except Exception:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()
            detail_font = ImageFont.load_default()
        draw.text((100, 180), title, fill=(230, 230, 230), font=title_font)
        draw.text((100, 300), subtitle, fill=(200, 200, 200), font=subtitle_font)
        draw.text((100, 360), detail, fill=(170, 170, 170), font=detail_font)
        draw.rectangle([(100, 440), (1500, 444)], fill=(90, 98, 110))
        return img

class AutoWakeApp:
    def __init__(self):
        self._mutex = single_instance_or_exit()
        self.cfg = load_config()
        self._running = False
        self._full_proc: subprocess.Popen | None = None
        self._last_full_launch_ts = 0.0
        self.root = tk.Tk()
        self.root.withdraw()
        self._saver = OverlaySaver(self.root, self.cfg.image_path)
        self._icon = None
        self._settings_window = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._ensure_chrome_launch()
        self._schedule_tick()
        self._refresh_menu()

    def stop(self):
        self._running = False
        self._saver.hide()
        self._refresh_menu()

    def update_config(self, new_cfg: AppConfig):
        self.cfg = new_cfg
        self._saver.image_path = new_cfg.image_path
        save_config(new_cfg)

    def _schedule_tick(self):
        if not self._running:
            return
        poll_ms = int(self.cfg.poll_sec * 1000)
        self.root.after(max(poll_ms, 100), self._tick)

    def _ensure_chrome_launch(self):
        log("===== START =====")
        if self._full_proc is None or self._full_proc.poll() is not None:
            self._full_proc = launch_fullscreen_site(self.cfg)
            self._last_full_launch_ts = time.time()

    def _tick(self):
        if not self._running:
            return
        cfg = self.cfg
        if cfg.chrome_repeat:
            if self._full_proc is None or self._full_proc.poll() is not None:
                now = time.time()
                if now - self._last_full_launch_ts >= cfg.chrome_relaunch_cooldown_sec:
                    log("FULL chrome not running -> relaunch")
                    self._full_proc = launch_fullscreen_site(cfg)
                    self._last_full_launch_ts = now

        idle = seconds_since_last_input()
        if cfg.saver_enabled:
            if idle <= cfg.active_threshold_sec:
                self._saver.hide()
            elif idle >= cfg.idle_to_show_sec:
                self._saver.show()
        else:
            self._saver.hide()

        self._saver.pump()
        self._schedule_tick()

    def _build_icon_image(self) -> Image.Image:
        size = 64
        img = Image.new("RGBA", (size, size), (30, 30, 30, 255))
        for i in range(8, size - 8):
            img.putpixel((i, 12), (255, 255, 255, 255))
            img.putpixel((i, size - 12), (255, 255, 255, 255))
        for j in range(12, size - 12):
            img.putpixel((8, j), (255, 255, 255, 255))
            img.putpixel((size - 8, j), (255, 255, 255, 255))
        return img

    def _open_settings(self, icon=None, item=None):
        self.root.after(0, self._show_settings_window)

    def _show_settings_window(self):
        if self._settings_window and tk.Toplevel.winfo_exists(self._settings_window):
            self._settings_window.lift()
            return

        cfg = self.cfg
        window = tk.Toplevel(self.root)
        window.title("AutoWake 설정")
        window.geometry("640x520")
        window.resizable(False, False)
        self._settings_window = window

        style = ttk.Style(window)
        for theme in ("vista", "xpnative", "clam"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue
        style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Section.TLabelframe", padding=12)
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Desc.TLabel", foreground="#5a5f6a")
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TFrame", background="#f5f6fa")
        style.configure("Header.TLabel", background="#f5f6fa")

        frm = ttk.Frame(window, padding=12)
        frm.pack(fill="both", expand=True)

        header = ttk.Frame(frm, style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="AutoWake 설정", style="Header.TLabel").pack(
            side="left"
        )
        ttk.Label(
            header,
            text="설정은 자동 저장됩니다.",
            style="Desc.TLabel",
        ).pack(side="left", padx=12)

        ttk.Separator(frm).pack(fill="x", pady=10)

        vars_map = {
            "url": tk.StringVar(value=cfg.url),
            "image_path": tk.StringVar(value=cfg.image_path),
            "idle_to_show_sec": tk.DoubleVar(value=cfg.idle_to_show_sec),
            "active_threshold_sec": tk.DoubleVar(value=cfg.active_threshold_sec),
            "poll_sec": tk.DoubleVar(value=cfg.poll_sec),
            "chrome_relaunch_cooldown_sec": tk.DoubleVar(
                value=cfg.chrome_relaunch_cooldown_sec
            ),
            "chrome_fullscreen": tk.BooleanVar(value=cfg.chrome_fullscreen),
            "chrome_kiosk": tk.BooleanVar(value=cfg.chrome_kiosk),
            "saver_enabled": tk.BooleanVar(value=cfg.saver_enabled),
            "chrome_repeat": tk.BooleanVar(value=cfg.chrome_repeat),
        }

        def apply_config():
            new_cfg = AppConfig(
                url=vars_map["url"].get(),
                image_path=vars_map["image_path"].get(),
                work_dir=cfg.work_dir,
                idle_to_show_sec=vars_map["idle_to_show_sec"].get(),
                active_threshold_sec=vars_map["active_threshold_sec"].get(),
                poll_sec=vars_map["poll_sec"].get(),
                chrome_relaunch_cooldown_sec=vars_map[
                    "chrome_relaunch_cooldown_sec"
                ].get(),
                chrome_fullscreen=vars_map["chrome_fullscreen"].get(),
                chrome_kiosk=vars_map["chrome_kiosk"].get(),
                saver_enabled=vars_map["saver_enabled"].get(),
                chrome_repeat=vars_map["chrome_repeat"].get(),
            )
            self.update_config(new_cfg)

        def on_change(*_args):
            apply_config()

        for key, var in vars_map.items():
            var.trace_add("write", on_change)

        notebook = ttk.Notebook(frm)
        notebook.pack(fill="both", expand=True)

        tab_general = ttk.Frame(notebook, padding=10)
        tab_saver = ttk.Frame(notebook, padding=10)
        tab_chrome = ttk.Frame(notebook, padding=10)
        notebook.add(tab_general, text="일반")
        notebook.add(tab_saver, text="세이버")
        notebook.add(tab_chrome, text="크롬")

        def browse_image():
            path = filedialog.askopenfilename(
                title="이미지 파일 선택",
                filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif")],
            )
            if path:
                vars_map["image_path"].set(path)

        general_box = ttk.Labelframe(
            tab_general, text="기본 정보", style="Section.TLabelframe"
        )
        general_box.pack(fill="x", pady=6)
        ttk.Label(general_box, text="시작 URL").grid(row=0, column=0, sticky="w")
        ttk.Entry(general_box, textvariable=vars_map["url"], width=60).grid(
            row=0, column=1, columnspan=2, sticky="ew", pady=4
        )
        ttk.Label(
            general_box,
            text="전체화면으로 열릴 웹 페이지 주소를 입력하세요.",
            style="Desc.TLabel",
        ).grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(general_box, text="이미지 파일 경로").grid(row=2, column=0, sticky="w")
        ttk.Entry(general_box, textvariable=vars_map["image_path"], width=60).grid(
            row=2, column=1, sticky="ew", pady=4
        )
        ttk.Button(general_box, text="찾기", command=browse_image).grid(
            row=2, column=2, padx=6
        )
        ttk.Label(
            general_box,
            text="세이버에 표시할 이미지 파일을 선택합니다.",
            style="Desc.TLabel",
        ).grid(row=3, column=1, columnspan=2, sticky="w")
        general_box.columnconfigure(1, weight=1)

        saver_box = ttk.Labelframe(
            tab_saver, text="세이버 동작", style="Section.TLabelframe"
        )
        saver_box.pack(fill="x", pady=6)
        ttk.Checkbutton(
            saver_box, text="세이버 사용", variable=vars_map["saver_enabled"]
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(saver_box, text="세이버 표시 대기(초)").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Spinbox(
            saver_box,
            from_=1,
            to=3600,
            textvariable=vars_map["idle_to_show_sec"],
            width=10,
        ).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(saver_box, text="활동 감지 임계(초)").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Spinbox(
            saver_box,
            from_=0.1,
            to=60,
            increment=0.1,
            textvariable=vars_map["active_threshold_sec"],
            width=10,
        ).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(saver_box, text="루프 주기(초)").grid(
            row=3, column=0, sticky="w"
        )
        ttk.Spinbox(
            saver_box,
            from_=0.1,
            to=10,
            increment=0.1,
            textvariable=vars_map["poll_sec"],
            width=10,
        ).grid(row=3, column=1, sticky="w", pady=4)

        chrome_box = ttk.Labelframe(
            tab_chrome, text="크롬 실행", style="Section.TLabelframe"
        )
        chrome_box.pack(fill="x", pady=6)
        ttk.Checkbutton(
            chrome_box, text="크롬 전체화면 시작", variable=vars_map["chrome_fullscreen"]
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(
            chrome_box, text="크롬 키오스크 모드", variable=vars_map["chrome_kiosk"]
        ).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(chrome_box, text="크롬 재실행 모드").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Radiobutton(
            chrome_box, text="반복", variable=vars_map["chrome_repeat"], value=True
        ).grid(row=2, column=1, sticky="w")
        ttk.Radiobutton(
            chrome_box, text="1회만", variable=vars_map["chrome_repeat"], value=False
        ).grid(row=2, column=2, sticky="w")
        ttk.Label(chrome_box, text="크롬 재실행 쿨다운(초)").grid(
            row=3, column=0, sticky="w"
        )
        ttk.Spinbox(
            chrome_box,
            from_=1,
            to=3600,
            textvariable=vars_map["chrome_relaunch_cooldown_sec"],
            width=10,
        ).grid(row=3, column=1, sticky="w", pady=4)

        footer = ttk.Frame(frm)
        footer.pack(fill="x", pady=8)

        def restore_defaults():
            defaults = AppConfig()
            vars_map["url"].set(defaults.url)
            vars_map["image_path"].set(defaults.image_path)
            vars_map["idle_to_show_sec"].set(defaults.idle_to_show_sec)
            vars_map["active_threshold_sec"].set(defaults.active_threshold_sec)
            vars_map["poll_sec"].set(defaults.poll_sec)
            vars_map["chrome_relaunch_cooldown_sec"].set(
                defaults.chrome_relaunch_cooldown_sec
            )
            vars_map["chrome_fullscreen"].set(defaults.chrome_fullscreen)
            vars_map["chrome_kiosk"].set(defaults.chrome_kiosk)
            vars_map["saver_enabled"].set(defaults.saver_enabled)
            vars_map["chrome_repeat"].set(defaults.chrome_repeat)

        def open_work_dir():
            try:
                os.startfile(cfg.work_dir)
            except Exception as e:
                log(f"OPEN work dir error: {e}")

        ttk.Button(footer, text="기본값 복원", command=restore_defaults).pack(
            side="left"
        )
        ttk.Button(footer, text="작업 폴더 열기", command=open_work_dir).pack(
            side="left", padx=6
        )
        ttk.Button(footer, text="닫기", command=window.destroy, style="Primary.TButton").pack(
            side="right"
        )

    def _exit_app(self, icon=None, item=None):
        self.stop()
        if self._icon:
            self._icon.stop()
        self.root.after(0, self.root.destroy)

    def _menu(self):
        def can_start(_item):
            return not self._running

        def can_stop(_item):
            return self._running

        def can_exit(_item):
            return self._running

        return pystray.Menu(
            pystray.MenuItem(
                "실행", lambda icon, item: self.root.after(0, self.start), enabled=can_start
            ),
            pystray.MenuItem(
                "중지", lambda icon, item: self.root.after(0, self.stop), enabled=can_stop
            ),
            pystray.MenuItem("설정", self._open_settings),
            pystray.MenuItem("종료", self._exit_app, enabled=can_exit),
        )

    def _refresh_menu(self):
        if self._icon:
            try:
                self._icon.update_menu()
            except Exception:
                pass

    def run(self):
        self.start()
        self._icon = pystray.Icon(
            "AutoWake",
            self._build_icon_image(),
            "AutoWake",
            self._menu(),
        )
        self._icon.run_detached()
        self.root.mainloop()


def main():
    app = AutoWakeApp()
    app.run()


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
