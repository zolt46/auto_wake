import argparse
import html
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict, replace
import atexit
import hashlib
import json
import os
import random
import re
import shutil
import shlex
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

# ================== 설정 ==================
DEFAULT_URL = "https://lib.koreatech.ac.kr/search/i-discovery"
DEFAULT_AUDIO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
DEFAULT_LOCAL_IMAGE = r"C:\AutoWake\default_saver.png"

WORK_DIR = r"C:\AutoWake"
DEFAULT_BUNDLED_IMAGE = os.path.join("assets", "default_saver.png")
DEFAULT_NOTICE_TITLE = "이용 안내"
DEFAULT_NOTICE_BODY = (
    "한국기술교육대학교 참고자료실 도서 검색 전용 PC입니다.\n\n"
    "본 PC는 학습·연구 목적의 정보 탐색을 위해 운영됩니다.\n"
    "올바른 사용을 권장드리며, 규정을 위반하는 경우 안내 및 조치가 이루어질 수 있습니다.\n\n"
    "이용해 주셔서 감사합니다."
)
DEFAULT_NOTICE_FOOTER = (
    "[전체화면/키오스크 종료 안내]\n"
    "• F11: 전체화면 해제\n"
    "• ESC: 일부 전체화면 해제\n"
    "• Alt + F4: 크롬 종료\n\n"
    "크롬이 종료되면 몇 초 후 자동으로 다시 실행됩니다.\n"
    "계속 이용하려면 크롬 창을 종료하지 않고 사용해 주세요."
)
DEFAULT_NOTICE_IMAGE_MODE = "bundled"
DEFAULT_NOTICE_IMAGE_HEIGHT = 120
DEFAULT_NOTICE_IMAGE_PATH = ""
DEFAULT_NOTICE_BUNDLED_IMAGE = "notice_default_1.png"
NOTICE_BUNDLED_IMAGES = [
    "notice_default_1.png",
    "notice_default_2.png",
]
NOTICE_BUNDLED_LABELS = {
    "notice_default_1.png": "기본 이미지 1",
    "notice_default_2.png": "기본 이미지 2",
}
NOTICE_WINDOW_PRESETS = {
    "auto": ("자동", (0, 0)),
    "compact": ("컴팩트", (520, 320)),
    "standard": ("표준", (640, 420)),
    "wide": ("와이드", (800, 420)),
    "large": ("대형", (900, 560)),
    "custom": ("수동 지정", (0, 0)),
}
NOTICE_FONT_FAMILIES = [
    "Noto Sans KR",
    "Malgun Gothic",
    "Nanum Gothic",
    "NanumSquare",
    "Apple SD Gothic Neo",
    "Segoe UI",
    "Arial",
]
NOTICE_STATE_FILE = "notice_state.json"
APP_ICON_PATH = os.path.join("assets", "icon.png")
APP_LOGO_PATH = os.path.join("assets", "logo.png")
APP_NAME = "AutoWake"
APP_VERSION = "1.0.1"
AUTHOR_NAME = "Zolt46 - PSW - Emanon108"
BUILD_DATE = "2026-01-30"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
# ==========================================


def config_file_path(work_dir: str) -> str:
    return os.path.join(work_dir, "config.json")


def notice_state_path(work_dir: str) -> str:
    return os.path.join(work_dir, NOTICE_STATE_FILE)


def worker_lock_path(work_dir: str, name: str) -> str:
    return os.path.join(work_dir, f"{name}.lock")


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        exit_code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return exit_code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def acquire_worker_lock(work_dir: str, name: str) -> Optional[str]:
    os.makedirs(work_dir, exist_ok=True)
    path = worker_lock_path(work_dir, name)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            pid = int(data.get("pid", 0))
            if _pid_is_running(pid):
                return None
            os.remove(path)
    except Exception as exc:
        log(f"WORKER lock read error: {exc}")
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"pid": os.getpid(), "started_at": time.time()}, file)
    except Exception as exc:
        log(f"WORKER lock write error: {exc}")
        return None
    return path


def release_worker_lock(path: Optional[str]) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as exc:
        log(f"WORKER lock remove error: {exc}")


def read_notice_state(work_dir: str) -> dict:
    path = notice_state_path(work_dir)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return {}


def write_notice_state(work_dir: str, **updates: float) -> None:
    os.makedirs(work_dir, exist_ok=True)
    state = read_notice_state(work_dir)
    state.update({key: float(value) for key, value in updates.items()})
    path = notice_state_path(work_dir)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False)
    os.replace(tmp_path, path)


def update_notice_state_counter(work_dir: str, key: str, delta: int) -> None:
    os.makedirs(work_dir, exist_ok=True)
    state = read_notice_state(work_dir)
    current = int(state.get(key, 0))
    state[key] = max(0, current + delta)
    path = notice_state_path(work_dir)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False)
    os.replace(tmp_path, path)


def log(msg: str) -> None:
    os.makedirs(WORK_DIR, exist_ok=True)
    path = os.path.join(WORK_DIR, "autowake.log")
    with open(path, "a", encoding="utf-8") as file:
        file.write(f"{datetime.now()} - {msg}\n")


def set_system_volume(percent: float) -> None:
    if sys.platform != "win32":
        return
    try:
        value = max(0, min(100, int(percent)))
        volume = int((value / 100) * 0xFFFF)
        packed = volume | (volume << 16)
        ctypes.windll.winmm.waveOutSetVolume(0, packed)
    except Exception as exc:
        log(f"VOLUME set error: {exc}")


def ensure_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


def load_app_icon() -> QtGui.QIcon:
    icon_path = resource_path(APP_ICON_PATH)
    if os.path.exists(icon_path):
        return QtGui.QIcon(icon_path)
    return QtGui.QIcon()


# ---------- 내부 중복 실행 방지(뮤텍스) ----------

def single_instance_or_exit(name="AutoWake_SingleInstance"):
    kernel32 = ctypes.windll.kernel32
    create_mutex = kernel32.CreateMutexW
    get_last_error = kernel32.GetLastError

    mutex = create_mutex(None, False, name)
    error_already_exists = 183
    if get_last_error() == error_already_exists:
        raise SystemExit("Already running")
    return mutex


# ----- WinAPI(Idle 체크) -----
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GetLastInputInfo = user32.GetLastInputInfo
GetTickCount64 = kernel32.GetTickCount64


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def seconds_since_last_input() -> float:
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    elapsed_ms = int(GetTickCount64()) - int(info.dwTime)
    return elapsed_ms / 1000.0


@dataclass
class AppConfig:
    url: str = DEFAULT_URL
    urls: list[str] = None
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
    ui_theme: str = "accent"
    saver_image_mode: str = "bundled"
    saver_display_mode: str = "full"
    audio_url: str = DEFAULT_AUDIO_URL
    audio_urls: list[str] = None
    audio_enabled: bool = True
    audio_window_mode: str = "minimized"
    audio_start_delay_sec: float = 2.0
    audio_relaunch_cooldown_sec: float = 10.0
    audio_repeat_mode: str = "repeat"
    audio_minimize_delay_sec: float = 10.0
    audio_launch_mode: str = "chrome"
    audio_pwa_app_id: str = ""
    audio_pwa_command_preview: str = ""
    audio_pwa_browser_hint: str = ""
    audio_pwa_arguments: str = ""
    audio_pwa_use_proxy: bool = False
    target_enabled: bool = True
    target_window_mode: str = "fullscreen"
    target_start_delay_sec: float = 1.0
    target_relaunch_cooldown_sec: float = 10.0
    target_refocus_interval_sec: float = 3.0
    target_repeat_mode: str = "repeat"
    saver_start_delay_sec: float = 1.0
    notice_enabled: bool = True
    notice_title: str = DEFAULT_NOTICE_TITLE
    notice_body: str = DEFAULT_NOTICE_BODY
    notice_footer: str = DEFAULT_NOTICE_FOOTER
    notice_body_font_size: int = 13
    notice_body_bold: bool = False
    notice_body_italic: bool = False
    notice_body_align: str = "left"
    notice_body_font_family: str = "Noto Sans KR"
    notice_footer_font_size: int = 12
    notice_footer_bold: bool = False
    notice_footer_italic: bool = False
    notice_footer_align: str = "left"
    notice_footer_font_family: str = "Noto Sans KR"
    notice_frame_color: str = "#0f172a"
    notice_frame_padding: int = 24
    notice_repeat_enabled: bool = False
    notice_repeat_interval_min: int = 30
    notice_window_width: int = 0
    notice_window_height: int = 0
    notice_window_preset: str = "auto"
    notice_image_mode: str = DEFAULT_NOTICE_IMAGE_MODE
    notice_image_path: str = DEFAULT_NOTICE_IMAGE_PATH
    notice_bundled_image: str = DEFAULT_NOTICE_BUNDLED_IMAGE
    notice_image_height: int = DEFAULT_NOTICE_IMAGE_HEIGHT
    admin_password: str = ""
    password_hash: str = ""
    password_salt: str = ""
    accent_theme: str = "sky"
    accent_color: str = ""

    def __post_init__(self):
        if self.urls is None:
            self.urls = [self.url]
        if self.audio_urls is None:
            self.audio_urls = [self.audio_url]

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        chrome_fullscreen = bool(data.get("chrome_fullscreen", True))
        chrome_kiosk = bool(data.get("chrome_kiosk", False))
        inferred_mode = "fullscreen" if chrome_fullscreen else "normal"
        if chrome_kiosk:
            inferred_mode = "kiosk"

        return cls(
            url=data.get("url", DEFAULT_URL),
            urls=list(data.get("urls", [])) or [data.get("url", DEFAULT_URL)],
            image_path=data.get("image_path", DEFAULT_LOCAL_IMAGE),
            work_dir=data.get("work_dir", WORK_DIR),
            idle_to_show_sec=float(data.get("idle_to_show_sec", 10.0)),
            active_threshold_sec=float(data.get("active_threshold_sec", 1.0)),
            poll_sec=float(data.get("poll_sec", 0.5)),
            chrome_relaunch_cooldown_sec=float(
                data.get("chrome_relaunch_cooldown_sec", 10.0)
            ),
            chrome_fullscreen=chrome_fullscreen,
            chrome_kiosk=chrome_kiosk,
            saver_enabled=bool(data.get("saver_enabled", True)),
            chrome_repeat=bool(data.get("chrome_repeat", True)),
            ui_theme="accent",
            saver_image_mode=str(data.get("saver_image_mode", "bundled")),
            saver_display_mode=str(data.get("saver_display_mode", "full")),
            audio_url=data.get("audio_url", DEFAULT_AUDIO_URL),
            audio_urls=list(data.get("audio_urls", [])) or [
                data.get("audio_url", DEFAULT_AUDIO_URL)
            ],
            audio_enabled=bool(data.get("audio_enabled", True)),
            audio_window_mode=data.get("audio_window_mode", "minimized"),
            audio_start_delay_sec=float(data.get("audio_start_delay_sec", 2.0)),
            audio_relaunch_cooldown_sec=float(
                data.get("audio_relaunch_cooldown_sec", 10.0)
            ),
            audio_repeat_mode=str(data.get("audio_repeat_mode", "repeat")),
            audio_minimize_delay_sec=float(data.get("audio_minimize_delay_sec", 10.0)),
            audio_launch_mode=str(data.get("audio_launch_mode", "chrome")),
            audio_pwa_app_id=str(data.get("audio_pwa_app_id", "")),
            audio_pwa_command_preview=str(data.get("audio_pwa_command_preview", "")),
            audio_pwa_browser_hint=str(data.get("audio_pwa_browser_hint", "")),
            audio_pwa_arguments=str(data.get("audio_pwa_arguments", "")),
            audio_pwa_use_proxy=bool(data.get("audio_pwa_use_proxy", False)),
            target_enabled=bool(data.get("target_enabled", True)),
            target_window_mode=data.get("target_window_mode", inferred_mode),
            target_start_delay_sec=float(data.get("target_start_delay_sec", 1.0)),
            target_relaunch_cooldown_sec=float(
                data.get("target_relaunch_cooldown_sec", 10.0)
            ),
            target_refocus_interval_sec=float(
                data.get("target_refocus_interval_sec", 3.0)
            ),
            target_repeat_mode=str(data.get("target_repeat_mode", "repeat")),
            saver_start_delay_sec=float(data.get("saver_start_delay_sec", 1.0)),
            notice_enabled=bool(data.get("notice_enabled", True)),
            notice_title=str(data.get("notice_title", DEFAULT_NOTICE_TITLE)),
            notice_body=str(data.get("notice_body", DEFAULT_NOTICE_BODY)),
            notice_footer=str(data.get("notice_footer", DEFAULT_NOTICE_FOOTER)),
            notice_body_font_size=int(data.get("notice_body_font_size", 13)),
            notice_body_bold=bool(data.get("notice_body_bold", False)),
            notice_body_italic=bool(data.get("notice_body_italic", False)),
            notice_body_align=str(data.get("notice_body_align", "left")),
            notice_body_font_family=str(data.get("notice_body_font_family", "Noto Sans KR")),
            notice_footer_font_size=int(data.get("notice_footer_font_size", 12)),
            notice_footer_bold=bool(data.get("notice_footer_bold", False)),
            notice_footer_italic=bool(data.get("notice_footer_italic", False)),
            notice_footer_align=str(data.get("notice_footer_align", "left")),
            notice_footer_font_family=str(data.get("notice_footer_font_family", "Noto Sans KR")),
            notice_frame_color=str(data.get("notice_frame_color", "#0f172a")),
            notice_frame_padding=int(data.get("notice_frame_padding", 24)),
            notice_repeat_enabled=bool(data.get("notice_repeat_enabled", False)),
            notice_repeat_interval_min=int(data.get("notice_repeat_interval_min", 30)),
            notice_window_width=int(data.get("notice_window_width", 0)),
            notice_window_height=int(data.get("notice_window_height", 0)),
            notice_window_preset=str(data.get("notice_window_preset", "auto")),
            notice_image_mode=str(data.get("notice_image_mode", DEFAULT_NOTICE_IMAGE_MODE)),
            notice_image_path=str(data.get("notice_image_path", DEFAULT_NOTICE_IMAGE_PATH)),
            notice_bundled_image=str(
                data.get("notice_bundled_image", DEFAULT_NOTICE_BUNDLED_IMAGE)
            ),
            notice_image_height=int(data.get("notice_image_height", DEFAULT_NOTICE_IMAGE_HEIGHT)),
            admin_password=str(data.get("admin_password", "")),
            password_hash=str(data.get("password_hash", "")),
            password_salt=str(data.get("password_salt", "")),
            accent_theme=str(data.get("accent_theme", "sky")),
            accent_color=str(data.get("accent_color", "")),
        )


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def create_password_hash(password: str) -> tuple[str, str]:
    salt = os.urandom(16).hex()
    return hash_password(password, salt), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    if not password_hash or not salt:
        return False
    return hash_password(password, salt) == password_hash


def load_config() -> AppConfig:
    os.makedirs(WORK_DIR, exist_ok=True)
    primary_path = config_file_path(WORK_DIR)
    if not os.path.exists(primary_path):
        cfg = AppConfig()
        save_config(cfg)
        return cfg
    try:
        with open(primary_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        cfg = AppConfig.from_dict(data)
        if cfg.work_dir and cfg.work_dir != WORK_DIR:
            alt_path = config_file_path(cfg.work_dir)
            if os.path.exists(alt_path):
                with open(alt_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                cfg = AppConfig.from_dict(data)
        if not cfg.password_hash:
            raw_password = data.get("admin_password", "") or "0000"
            cfg.password_hash, cfg.password_salt = create_password_hash(raw_password)
            cfg.admin_password = ""
            save_config(cfg)
        return cfg
    except Exception as exc:
        log(f"CONFIG load error: {exc}")
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    work_dir = cfg.work_dir or WORK_DIR
    os.makedirs(work_dir, exist_ok=True)
    data = asdict(cfg)
    try:
        with open(config_file_path(work_dir), "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"CONFIG save error: {exc}")


def _blend_with_white(hex_color: str, ratio: float) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = int(r + (255 - r) * ratio)
    g = int(g + (255 - g) * ratio)
    b = int(b + (255 - b) * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


def _blend_with_black(hex_color: str, ratio: float) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = int(r * (1 - ratio))
    g = int(g * (1 - ratio))
    b = int(b * (1 - ratio))
    return f"#{r:02x}{g:02x}{b:02x}"


def _normalize_hex_color(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("#"):
        value = f"#{value}"
    if len(value) == 4:
        value = f"#{value[1] * 2}{value[2] * 2}{value[3] * 2}"
    return value.lower()


def build_palette(accent_theme: str, accent_color: str = "") -> dict:
    accents = {
        "sky": ("#0ea5e9", "#38bdf8"),
        "indigo": ("#6366f1", "#818cf8"),
        "emerald": ("#10b981", "#34d399"),
        "rose": ("#f43f5e", "#fb7185"),
        "amber": ("#f59e0b", "#fbbf24"),
        "teal": ("#14b8a6", "#2dd4bf"),
        "violet": ("#8b5cf6", "#a78bfa"),
        "lime": ("#84cc16", "#a3e635"),
        "cyan": ("#06b6d4", "#22d3ee"),
        "pink": ("#ec4899", "#f472b6"),
    }
    accent, accent_soft = accents.get(accent_theme, accents["sky"])
    background_variants = {
        "sky": ("#e0f2fe", "#f0f9ff", "#dbeafe", "#bae6fd", "#f8fafc"),
        "indigo": ("#e0e7ff", "#eef2ff", "#c7d2fe", "#a5b4fc", "#f8fafc"),
        "emerald": ("#dcfce7", "#ecfdf5", "#bbf7d0", "#86efac", "#f8fafc"),
        "rose": ("#ffe4e6", "#fff1f2", "#fecdd3", "#fda4af", "#f8fafc"),
        "amber": ("#fef3c7", "#fffbeb", "#fde68a", "#fcd34d", "#f8fafc"),
        "teal": ("#ccfbf1", "#f0fdfa", "#99f6e4", "#5eead4", "#f8fafc"),
        "violet": ("#ede9fe", "#f5f3ff", "#ddd6fe", "#c4b5fd", "#f8fafc"),
        "lime": ("#ecfccb", "#f7fee7", "#d9f99d", "#bef264", "#f8fafc"),
        "cyan": ("#cffafe", "#ecfeff", "#a5f3fc", "#67e8f9", "#f8fafc"),
        "pink": ("#fce7f3", "#fdf2f8", "#fbcfe8", "#f9a8d4", "#f8fafc"),
    }
    bg, card, card_alt, topbar, tab_bg = background_variants.get(
        accent_theme, background_variants["sky"]
    )
    accent_color = _normalize_hex_color(accent_color)
    if accent_color:
        accent = accent_color
        accent_soft = _blend_with_white(accent, 0.35)
        base_bg = _blend_with_white(accent, 0.9)
        bg = _blend_with_black(base_bg, 0.08)
        card = _blend_with_black(_blend_with_white(accent, 0.92), 0.05)
        card_alt = _blend_with_black(_blend_with_white(accent, 0.95), 0.04)
        topbar = _blend_with_black(_blend_with_white(accent, 0.86), 0.12)
        tab_bg = _blend_with_black(_blend_with_white(accent, 0.88), 0.1)
    else:
        bg = _blend_with_white(bg, 0.03)
        card = _blend_with_white(card, 0.02)
        card_alt = _blend_with_white(card_alt, 0.02)
        tab_bg = _blend_with_white(tab_bg, 0.02)

        bg = _blend_with_black(bg, 0.08)
        card = _blend_with_black(card, 0.06)
        card_alt = _blend_with_black(card_alt, 0.06)
        tab_bg = _blend_with_black(tab_bg, 0.1)
    accent_dark = _blend_with_black(accent, 0.32)
    tab_active = _blend_with_black(tab_bg, 0.24)
    border = _blend_with_black(tab_bg, 0.18)
    return {
        "bg": bg,
        "bg_card": card,
        "bg_card_alt": card_alt,
        "accent": accent,
        "accent_soft": accent_soft,
        "accent_dark": accent_dark,
        "text_primary": "#0f172a",
        "text_muted": "#475569",
        "border": border,
        "bg_dark": "#0f172a",
        "tab_bg": tab_bg,
        "tab_active": tab_active,
        "tab_text": "#334155",
        "topbar": topbar,
        "dialog_bg": card_alt,
        "dialog_text": "#0f172a",
        "dialog_border": "#cbd5f5",
    }


def find_chrome_exe() -> str:
    env_candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(
            os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"
        ),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(
            os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"
        ),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for path in [*CHROME_CANDIDATES, *env_candidates]:
        if path and os.path.exists(path):
            return path
    for candidate in ("chrome", "msedge"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    log("Chrome/Edge executable not found; falling back to 'chrome' in PATH.")
    return "chrome"


def _iter_manifest_candidates(user_data_dir: str) -> list[str]:
    manifests: list[str] = []
    if not user_data_dir or not os.path.exists(user_data_dir):
        return manifests
    for root, _dirs, files in os.walk(user_data_dir):
        if "Web Applications" not in root:
            continue
        if "manifest.json" in files:
            manifests.append(os.path.join(root, "manifest.json"))
    return manifests


def _extract_app_id(entry: dict) -> Optional[str]:
    app_id = entry.get("app_id") or entry.get("id")
    if isinstance(app_id, str) and app_id:
        return app_id
    return None


def _scan_for_youtube_app_id(data: object) -> Optional[str]:
    if isinstance(data, dict):
        name = str(data.get("name", "")).lower()
        short_name = str(data.get("short_name", "")).lower()
        if "youtube" in name or "youtube" in short_name:
            app_id = _extract_app_id(data)
            if app_id:
                return app_id
        for value in data.values():
            found = _scan_for_youtube_app_id(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _scan_for_youtube_app_id(item)
            if found:
                return found
    return None


def detect_youtube_pwa_from_shortcuts() -> tuple[str, str, str, bool]:
    if sys.platform != "win32":
        return "", "", "", False
    start_menu_roots = [
        os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
        ),
        os.path.join(
            os.environ.get("PROGRAMDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
        ),
    ]
    app_folders = [
        "Chrome Apps",
        "Chrome 앱",
        "Microsoft Edge Apps",
        "Microsoft Edge 앱",
    ]
    candidate_dirs = []
    for root in start_menu_roots:
        if not root or not os.path.exists(root):
            continue
        for folder in app_folders:
            candidate = os.path.join(root, folder)
            if os.path.exists(candidate):
                candidate_dirs.append(candidate)
    fallback_roots = [root for root in start_menu_roots if root and os.path.exists(root)]
    search_dirs = candidate_dirs or fallback_roots
    for root in search_dirs:
        limit_to_youtube = root in fallback_roots and not candidate_dirs
        if not os.path.exists(root):
            continue
        for current_root, _dirs, files in os.walk(root):
            for name in files:
                if not name.lower().endswith(".lnk"):
                    continue
                if limit_to_youtube and "youtube" not in name.lower():
                    continue
                link_path = os.path.join(current_root, name)
                try:
                    safe_link_path = link_path.replace("'", "''")
                    command = (
                        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
                        f"'{safe_link_path}'"
                        ");"
                        "$s.TargetPath + '|' + $s.Arguments"
                    )
                    cmd = ["powershell", "-NoProfile", "-Command", command]
                    output = subprocess.check_output(cmd, text=True).strip()
                except Exception:
                    continue
                if "|" not in output:
                    continue
                target_path, arguments = output.split("|", 1)
                target_path = target_path.strip().strip('"')
                arguments = arguments.strip()
                match = re.search(r"--app-id=([a-zA-Z0-9]+)", arguments)
                if match:
                    app_id = match.group(1)
                    launcher = target_path.strip().strip('"')
                    if launcher:
                        return app_id, launcher, arguments.strip(), "chrome_proxy" in launcher.lower()
    return "", "", "", False


def detect_youtube_pwa_app_id() -> tuple[str, str, str, bool]:
    shortcut_app_id, shortcut_launcher, shortcut_args, using_proxy = detect_youtube_pwa_from_shortcuts()
    if shortcut_app_id:
        return shortcut_app_id, shortcut_launcher, shortcut_args, using_proxy
    candidates = [
        (
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"),
            "chrome",
        ),
        (
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data"),
            "msedge",
        ),
    ]
    for user_data_dir, browser_hint in candidates:
        for manifest_path in _iter_manifest_candidates(user_data_dir):
            try:
                with open(manifest_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            except Exception:
                continue
            app_id = _scan_for_youtube_app_id(data)
            if app_id:
                return app_id, browser_hint, "", False
    return "", "", "", False


def _clean_launch_url_arg(launcher_args: str) -> str:
    if not launcher_args:
        return ""
    cleaned = re.sub(
        r"--app-launch-url-for-shortcuts-menu-item=\\\".*?\\\"",
        "",
        launcher_args,
    )
    cleaned = re.sub(
        r"--app-launch-url-for-shortcuts-menu-item=\".*?\"",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"--app-launch-url-for-shortcuts-menu-item=\\S+",
        "",
        cleaned,
    )
    return " ".join(cleaned.split())


def build_pwa_command_preview(
    app_id: str,
    browser_hint: str,
    launcher_args: str,
    url: str,
    random_mode: bool,
) -> str:
    if not app_id:
        return ""
    launch_url_arg = ""
    if url:
        launch_url_arg = f'--app-launch-url-for-shortcuts-menu-item="{url}"'
    cleaned_args = _clean_launch_url_arg(launcher_args)
    if os.path.isfile(browser_hint):
        base = f"{browser_hint} {cleaned_args}".strip()
        preview_items = [base, launch_url_arg]
        if random_mode:
            preview_items.append("# 랜덤 URL은 실행 시 선택됩니다.")
        return " ".join(item for item in preview_items if item)
    browser = find_chrome_exe()
    if browser_hint == "msedge":
        edge = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe")
        if edge and os.path.exists(edge):
            browser = edge
    base = f"{browser} --app-id={app_id} --autoplay-policy=no-user-gesture-required".strip()
    preview_items = [base, launch_url_arg]
    if random_mode:
        preview_items.append("# 랜덤 URL은 실행 시 선택됩니다.")
    return " ".join(item for item in preview_items if item)


def launch_pwa(
    app_id: str,
    browser_hint: str,
    launcher_args: str,
    url: str,
) -> Optional[subprocess.Popen]:
    if not app_id:
        return None
    browser_candidate = browser_hint.strip().strip('"')
    if os.path.isfile(browser_candidate):
        browser = browser_candidate
    else:
        browser = find_chrome_exe()
        if browser_hint == "msedge":
            edge = os.path.join(
                os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"
            )
            if edge and os.path.exists(edge):
                browser = edge
    args = [browser]
    cleaned_args = _clean_launch_url_arg(launcher_args)
    if cleaned_args:
        args.extend(shlex.split(cleaned_args, posix=False))
    else:
        args.extend(
            [
                f"--app-id={app_id}",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-background-mode",
                "--disable-backgrounding-occluded-windows",
            ]
        )
    if url:
        args.append(f"--app-launch-url-for-shortcuts-menu-item={url}")
    try:
        log(f"Launching PWA: {args}")
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        log(f"ERROR launching PWA: {exc}")
        return None


def build_chrome_args(
    urls: list[str],
    profile_dir: str,
    mode: str,
    autoplay: bool,
    disable_background: bool = False,
) -> list[str]:
    chrome = find_chrome_exe()
    args = [
        chrome,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
    ]
    if autoplay:
        args.append("--autoplay-policy=no-user-gesture-required")
    if disable_background:
        args.append("--disable-background-mode")
        args.append("--disable-backgrounding-occluded-windows")
    mode = (mode or "normal").lower()
    if mode == "minimized":
        args.append("--start-minimized")
    elif mode == "fullscreen":
        args.append("--start-fullscreen")
    elif mode == "kiosk":
        args.append("--kiosk")
    args.extend(urls)
    return args


def ensure_youtube_autoplay(url: str) -> str:
    if "youtube.com" not in url and "youtu.be" not in url:
        return url
    if "autoplay=" in url:
        return url
    connector = "&" if "?" in url else "?"
    return f"{url}{connector}autoplay=1&mute=0&playsinline=1"


def launch_chrome(
    urls: list[str],
    profile_dir: str,
    mode: str,
    autoplay: bool,
    disable_background: bool = False,
) -> Optional[subprocess.Popen]:
    args = build_chrome_args(urls, profile_dir, mode, autoplay, disable_background)
    try:
        log(f"Launching chrome: {args}")
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        log(f"ERROR launching chrome: {exc}")
        return None


def find_window_handles_by_pid(pid: int) -> list[int]:
    handles: list[int] = []

    def enum_callback(hwnd, lparam):
        is_visible = user32.IsWindowVisible(hwnd)
        if not is_visible:
            return True
        found_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(found_pid))
        if found_pid.value == pid:
            handles.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_callback), 0)
    return handles


def keep_window_on_top(pid: int) -> None:
    handles = find_window_handles_by_pid(pid)
    for hwnd in handles:
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
        user32.SetForegroundWindow(hwnd)


def minimize_window(pid: int) -> None:
    handles = find_window_handles_by_pid(pid)
    for hwnd in handles:
        user32.ShowWindow(hwnd, 6)


def restore_window(pid: int) -> None:
    handles = find_window_handles_by_pid(pid)
    for hwnd in handles:
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)


def terminate_process(pid: int) -> None:
    if not pid:
        return
    try:
        if os.name == "nt":
            creationflags = (
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            )
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                check=False,
            )
        else:
            os.kill(pid, 15)
    except Exception:
        pass


def find_chrome_processes_by_profile(profile_dir: str) -> list[int]:
    if os.name != "nt" or not profile_dir:
        return []
    try:
        escaped = profile_dir.replace("\\", "\\\\")
        query = f"CommandLine like '%--user-data-dir={escaped}%'"
        creationflags = (
            subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        output = subprocess.check_output(
            ["wmic", "process", "where", query, "get", "ProcessId,CommandLine", "/format:csv"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in output.splitlines():
        if "--user-data-dir" not in line:
            continue
        parts = [part for part in line.split(",") if part]
        if not parts:
            continue
        pid_str = parts[-1].strip()
        if pid_str.isdigit():
            pids.append(int(pid_str))
    return pids


def find_chrome_processes_by_app_id(app_id: str) -> list[int]:
    if os.name != "nt" or not app_id:
        return []
    try:
        query = f"CommandLine like '%--app-id={app_id}%'"
        creationflags = (
            subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        output = subprocess.check_output(
            ["wmic", "process", "where", query, "get", "ProcessId,CommandLine", "/format:csv"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in output.splitlines():
        if "--app-id" not in line:
            continue
        parts = [part for part in line.split(",") if part]
        if not parts:
            continue
        pid_str = parts[-1].strip()
        if pid_str.isdigit():
            pids.append(int(pid_str))
    return pids


def _normalize_notice_text(value: str, fallback: str) -> str:
    if value is None:
        return fallback
    if value.strip() == "":
        return fallback
    return value


def _notice_alignment(value: str) -> QtCore.Qt.Alignment:
    mapping = {
        "left": QtCore.Qt.AlignLeft,
        "center": QtCore.Qt.AlignHCenter,
        "right": QtCore.Qt.AlignRight,
    }
    return mapping.get(value, QtCore.Qt.AlignLeft) | QtCore.Qt.AlignTop


def _build_notice_font(family: str, size: int, bold: bool, italic: bool) -> QtGui.QFont:
    font = QtGui.QFont(family or "Noto Sans KR", int(size))
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    return font


def _notice_style(font: QtGui.QFont) -> str:
    weight = "700" if font.bold() else "500"
    style = "italic" if font.italic() else "normal"
    size = font.pointSize() if font.pointSize() > 0 else 12
    family = font.family().replace("'", "\\'")
    return f"font-family: '{family}'; font-size: {size}px; font-weight: {weight}; font-style: {style};"


def build_notice_content(cfg: AppConfig) -> tuple[str, str, str]:
    title = (cfg.notice_title or "").strip() or DEFAULT_NOTICE_TITLE
    body = _normalize_notice_text(cfg.notice_body, DEFAULT_NOTICE_BODY)
    footer = _normalize_notice_text(cfg.notice_footer, DEFAULT_NOTICE_FOOTER)
    return title, body, footer


def resolve_notice_image_path(cfg: AppConfig) -> str:
    mode = (cfg.notice_image_mode or DEFAULT_NOTICE_IMAGE_MODE).lower()
    if mode == "none":
        return ""
    if mode == "path":
        path = cfg.notice_image_path
    else:
        filename = cfg.notice_bundled_image or DEFAULT_NOTICE_BUNDLED_IMAGE
        path = resource_path(os.path.join("assets", filename))
    if path and os.path.exists(path):
        return path
    return ""


def resolve_notice_window_size(cfg: AppConfig) -> tuple[int, int]:
    width = int(cfg.notice_window_width or 0)
    height = int(cfg.notice_window_height or 0)
    if width > 0 and height > 0:
        return width, height
    preset = (cfg.notice_window_preset or "auto").lower()
    _, size = NOTICE_WINDOW_PRESETS.get(preset, NOTICE_WINDOW_PRESETS["auto"])
    return size


class StyledToggle(QtWidgets.QAbstractButton):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self._label = QtWidgets.QLabel(label, self)
        self._label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        self._palette = {
            "accent": "#0ea5e9",
            "bg_card_alt": "#1f2937",
            "text_primary": "#f9fafb",
            "text_muted": "#94a3b8",
            "knob": "#0b1220",
        }
        self.setMinimumHeight(32)
        self.setMinimumWidth(260)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def set_palette(self, palette: dict) -> None:
        self._palette = {
            "accent": palette["accent"],
            "bg_card_alt": palette["bg_card_alt"],
            "accent_dark": palette["accent_dark"],
            "text_primary": palette["text_primary"],
            "text_muted": palette["text_muted"],
            "knob": palette["bg"],
        }
        self._label.setStyleSheet(
            f"color: {palette['text_primary']}; font-weight: 700; font-size: 14px;"
        )
        self.update()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(280, 32)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        self._label.setGeometry(60, 0, self.width() - 60, self.height())

    def paintEvent(self, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        toggle_width = 46
        toggle_height = 24
        x = 0
        y = (self.height() - toggle_height) // 2
        radius = toggle_height / 2

        if self.isChecked():
            track_color = QtGui.QColor(self._palette["accent"])
            knob_x = x + toggle_width - toggle_height + 2
        else:
            track_color = QtGui.QColor(self._palette["accent_dark"])
            knob_x = x + 2

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(x, y, toggle_width, toggle_height, radius, radius)
        painter.setBrush(QtGui.QColor(self._palette["knob"]))
        painter.drawEllipse(QtCore.QRectF(knob_x, y + 2, toggle_height - 4, toggle_height - 4))


class StepperInput(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.minus_button = QtWidgets.QPushButton("▼")
        self.minus_button.setObjectName("StepperButton")
        self.plus_button = QtWidgets.QPushButton("▲")
        self.plus_button.setObjectName("StepperButton")
        arrow_font = QtGui.QFont()
        arrow_font.setPointSize(12)
        arrow_font.setBold(True)
        for button in (self.minus_button, self.plus_button):
            button.setFixedSize(28, 28)
            button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            button.setFont(arrow_font)

        self.spin = QtWidgets.QDoubleSpinBox()
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin.setAlignment(QtCore.Qt.AlignCenter)
        self.spin.valueChanged.connect(self.valueChanged.emit)
        self.spin.setFixedWidth(64)

        self.minus_button.clicked.connect(lambda: self.spin.stepBy(-1))
        self.plus_button.clicked.connect(lambda: self.spin.stepBy(1))

        layout.addWidget(self.minus_button)
        layout.addWidget(self.spin)
        layout.addWidget(self.plus_button)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def setRange(self, minimum: float, maximum: float) -> None:
        self.spin.setRange(minimum, maximum)

    def setSingleStep(self, step: float) -> None:
        self.spin.setSingleStep(step)

    def setDecimals(self, decimals: int) -> None:
        self.spin.setDecimals(decimals)

    def setValue(self, value: float) -> None:
        self.spin.setValue(value)

    def value(self) -> float:
        return self.spin.value()


class ModeSelector(QtWidgets.QWidget):
    currentTextChanged = QtCore.Signal(str)

    def __init__(self, options: list[str], parent=None, labels: Optional[dict[str, str]] = None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QtWidgets.QPushButton] = {}
        self._labels = labels or {}
        for option in options:
            button = QtWidgets.QPushButton(self._labels.get(option, option))
            button.setCheckable(True)
            button.setObjectName("ModeButton")
            self._group.addButton(button)
            self._buttons[option] = button
            layout.addWidget(button)
        if options:
            self._buttons[options[0]].setChecked(True)
        self._group.buttonClicked.connect(self._emit_current_text)

    def _emit_current_text(self):
        self.currentTextChanged.emit(self.currentText())

    def currentText(self) -> str:
        for option, button in self._buttons.items():
            if button.isChecked():
                return option
        return ""

    def setCurrentText(self, text: str) -> None:
        button = self._buttons.get(text)
        if button:
            button.setChecked(True)
            self._emit_current_text()

    def setOptionEnabled(self, option: str, enabled: bool) -> None:
        button = self._buttons.get(option)
        if button:
            button.setEnabled(enabled)

    def setEnabledOptions(self, enabled_options: set[str]) -> None:
        for option, button in self._buttons.items():
            button.setEnabled(option in enabled_options)

class FancyCard(QtWidgets.QFrame):
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FancyCard")
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)

        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("CardTitle")
        subtitle_label = QtWidgets.QLabel(subtitle)
        subtitle_label.setObjectName("CardSubtitle")
        subtitle_label.setWordWrap(True)
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)
        layout.addWidget(subtitle_label)
        self.body_layout = QtWidgets.QVBoxLayout()
        layout.addLayout(self.body_layout)


class ClickableLabel(QtWidgets.QLabel):
    doubleClicked = QtCore.Signal()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class EasterEggDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AutoWake Secret Studio")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(
            """
            QDialog { background-color: #0F172A; }
            QLabel[popup-role="body"], QLabel[popup-role="hint"] { color: #E2E8F0; }
            """
        )
        layout = QtWidgets.QVBoxLayout(self)
        icon = load_app_icon()
        if not icon.isNull():
            icon_label = QtWidgets.QLabel()
            icon_label.setAlignment(QtCore.Qt.AlignCenter)
            icon_label.setPixmap(icon.pixmap(64, 64))
            layout.addWidget(icon_label)
        ascii_art = r"""
 █████╗ ██╗   ██╗████████╗ ██████╗ ██╗    ██╗ █████╗ ██╗  ██╗███████╗
██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗██║    ██║██╔══██╗██║ ██╔╝██╔════╝
███████║██║   ██║   ██║   ██║   ██║██║ █╗ ██║███████║█████╔╝ █████╗  
██╔══██║██║   ██║   ██║   ██║   ██║██║███╗██║██╔══██║██╔═██╗ ██╔══╝  
██║  ██║╚██████╔╝   ██║   ╚██████╔╝╚███╔███╔╝██║  ██║██║  ██╗███████╗
╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
        """.strip("\n")
        label = QtWidgets.QLabel(
            "<pre style='color:#2FF5C9; font-family: "
            "Cascadia Code, Consolas, monospace; font-size: 15px; font-weight:700;'>"
            f"{html.escape(ascii_art)}"
            "</pre>"
        )
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(label)
        message = QtWidgets.QLabel(
            "숨은 공방을 찾아내셨군요!\n"
            "부드럽게 시작되는 자동화의 순간을 위해,\n"
            "AutoWake가 오늘도 함께합니다."
        )
        message.setAlignment(QtCore.Qt.AlignCenter)
        message.setWordWrap(True)
        message.setProperty("popup-role", "body")
        message.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(message)
        quote = QtWidgets.QLabel(
            "<i>“좋은 하루는 자연스러운 시작에서 비롯됩니다.”<br>"
            "— AutoWake 비밀 노트</i>"
        )
        quote.setAlignment(QtCore.Qt.AlignCenter)
        quote.setProperty("popup-role", "hint")
        quote.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(quote)


class UrlListDialog(QtWidgets.QDialog):
    def __init__(self, title: str, urls: list[str], palette: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(460, 360)
        self._palette = palette
        self._urls = urls

        layout = QtWidgets.QVBoxLayout(self)
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.addItems(urls)
        list_row = QtWidgets.QHBoxLayout()
        list_row.addWidget(self.list_widget, 1)
        move_column = QtWidgets.QVBoxLayout()
        move_column.addStretch()
        self.move_up_button = QtWidgets.QPushButton("위로")
        self.move_down_button = QtWidgets.QPushButton("아래로")
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        move_column.addWidget(self.move_up_button)
        move_column.addWidget(self.move_down_button)
        move_column.addStretch()
        list_row.addLayout(move_column)
        layout.addLayout(list_row)

        input_row = QtWidgets.QHBoxLayout()
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        add_button = QtWidgets.QPushButton("추가")
        remove_button = QtWidgets.QPushButton("삭제")
        add_button.clicked.connect(self._add_url)
        remove_button.clicked.connect(self._remove_selected)
        input_row.addWidget(self.url_input)
        input_row.addWidget(add_button)
        input_row.addWidget(remove_button)
        layout.addLayout(input_row)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        ok = QtWidgets.QPushButton("확인")
        cancel = QtWidgets.QPushButton("취소")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        button_row.addWidget(cancel)
        button_row.addWidget(ok)
        layout.addLayout(button_row)

        self.setStyleSheet(
            " ".join(
                [
                    f"QDialog {{ background: {palette['dialog_bg']}; color: {palette['dialog_text']}; }}",
                    f"QDialog QLabel {{ color: {palette['dialog_text']}; }}",
                    f"QDialog QLineEdit {{ background: {palette['bg_card']};"
                    f" border: 1px solid {palette['dialog_border']};"
                    " border-radius: 8px; padding: 6px 10px;",
                    f" color: {palette['dialog_text']}; }}",
                    f"QDialog QPushButton {{ background: {palette['accent']}; color: #0b1220;",
                    " border-radius: 10px; padding: 6px 12px; font-weight: 700; }}",
                    f"QListWidget {{ background: {palette['bg_card']};"
                    f" border: 1px solid {palette['dialog_border']};"
                    f" color: {palette['dialog_text']}; }}",
                ]
            )
        )

    def _add_url(self):
        text = self.url_input.text().strip()
        if not text:
            return
        self.list_widget.addItem(text)
        self.url_input.clear()

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def _move_selected(self, delta: int) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        target = row + delta
        if target < 0 or target >= self.list_widget.count():
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(target, item)
        self.list_widget.setCurrentRow(target)

    def urls(self) -> list[str]:
        return [
            self.list_widget.item(index).text().strip()
            for index in range(self.list_widget.count())
            if self.list_widget.item(index).text().strip()
        ]


class WarningDialog(QtWidgets.QDialog):
    def __init__(self, message: str, palette: dict, work_dir: str, parent=None):
        super().__init__(parent)
        self._work_dir = work_dir
        self.setWindowTitle("비밀번호 오류")
        self.setModal(True)
        self.setFixedSize(300, 140)
        layout = QtWidgets.QVBoxLayout(self)
        content = QtWidgets.QHBoxLayout()
        icon_label = QtWidgets.QLabel()
        icon = self.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning)
        icon_label.setPixmap(icon.pixmap(36, 36))
        icon_label.setAlignment(QtCore.Qt.AlignTop)
        content.addWidget(icon_label)
        label = QtWidgets.QLabel(message)
        label.setWordWrap(True)
        content.addWidget(label, 1)
        layout.addLayout(content)
        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        ok = QtWidgets.QPushButton("확인")
        ok.setAutoDefault(False)
        ok.clicked.connect(self.accept)
        button_row.addWidget(ok)
        layout.addLayout(button_row)
        self.setStyleSheet(
            " ".join(
                [
                    f"QDialog {{ background: {palette['dialog_bg']}; color: {palette['dialog_text']}; }}",
                    f"QDialog QLabel {{ color: {palette['dialog_text']}; }}",
                    f"QDialog QPushButton {{ background: {palette['accent']}; color: #0b1220;",
                    " border-radius: 10px; padding: 6px 12px; font-weight: 700; }}",
                ]
            )
        )

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        update_notice_state_counter(self._work_dir, "ui_active", 1)
        super().showEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        update_notice_state_counter(self._work_dir, "ui_active", -1)
        super().hideEvent(event)


class PasswordDialog(QtWidgets.QDialog):
    def __init__(self, verifier, palette: dict, work_dir: str, parent=None):
        super().__init__(parent)
        self._work_dir = work_dir
        self.setWindowTitle("보안 확인")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.setFixedSize(320, 180)
        self._verifier = verifier
        self._palette = palette
        self._warning_open = False
        self._warning_dialog: Optional[WarningDialog] = None
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("설정에 들어가려면 비밀번호를 입력하세요."))
        self.input = QtWidgets.QLineEdit()
        self.input.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.input)
        self.message = QtWidgets.QLabel("")
        self.message.setStyleSheet("color: #ef4444;")
        layout.addWidget(self.message)
        buttons = QtWidgets.QHBoxLayout()
        cancel = QtWidgets.QPushButton("취소")
        ok = QtWidgets.QPushButton("확인")
        ok.setAutoDefault(False)
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept_with_validation)
        self.input.returnPressed.connect(self._accept_with_validation)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)
        self._action_buttons = [cancel, ok]
        self.input.setFocus()
        self.setStyleSheet(
            " ".join(
                [
                    f"QDialog {{ background: {palette['dialog_bg']}; color: {palette['dialog_text']}; }}",
                    f"QDialog QLabel {{ color: {palette['dialog_text']}; }}",
                    f"QDialog QLineEdit {{ background: {palette['bg_card']};"
                    f" border: 1px solid {palette['dialog_border']};"
                    " border-radius: 8px; padding: 6px 10px;",
                    f" color: {palette['dialog_text']}; }}",
                    f"QDialog QPushButton {{ background: {palette['accent']}; color: #0b1220;",
                    " border-radius: 10px; padding: 6px 12px; font-weight: 700; }}",
                    f"QMessageBox {{ background: {palette['dialog_bg']}; color: {palette['dialog_text']}; }}",
                    f"QMessageBox QLabel {{ color: {palette['dialog_text']}; }}",
                    f"QMessageBox QPushButton {{ background: {palette['accent']}; color: #0b1220;",
                    " border-radius: 10px; padding: 6px 12px; font-weight: 700; }}",
                ]
            )
        )

    def _show_warning(self, message: str) -> None:
        self._warning_open = True
        self.input.setEnabled(False)
        for button in self._action_buttons:
            button.setEnabled(False)
        try:
            self.input.returnPressed.disconnect(self._accept_with_validation)
        except TypeError:
            pass
        self._warning_dialog = WarningDialog(message, self._palette, self._work_dir, self)
        self._warning_dialog.finished.connect(self._restore_focus)
        self._warning_dialog.open()

    def _restore_focus(self) -> None:
        self._warning_open = False
        self.input.setEnabled(True)
        for button in self._action_buttons:
            button.setEnabled(True)
        try:
            self.input.returnPressed.disconnect(self._accept_with_validation)
        except TypeError:
            pass
        self.input.returnPressed.connect(self._accept_with_validation)
        self.show()
        self.raise_()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        update_notice_state_counter(self._work_dir, "ui_active", 1)
        super().showEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        update_notice_state_counter(self._work_dir, "ui_active", -1)
        super().hideEvent(event)
        self.activateWindow()
        self.input.setFocus()
        self._warning_dialog = None

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if self._warning_open and event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            event.ignore()
            return
        super().keyPressEvent(event)

    def _accept_with_validation(self):
        value = self.input.text().strip()
        if not value:
            self.message.setText("\n비밀번호를 입력하세요.")
            self._show_warning("\n비밀번호를 입력하세요.")
            return
        if not self._verifier(value):
            self.message.setText("비밀번호가 올바르지 않습니다.\n다시 입력해 주세요.")
            self._show_warning("비밀번호가 올바르지 않습니다.\n다시 입력해 주세요.")
            self.input.clear()
            self.input.selectAll()
            self.input.setFocus()
            self.show()
            self.raise_()
            self.activateWindow()
            return
        self.accept()


class PasswordChangeDialog(QtWidgets.QDialog):
    def __init__(self, palette: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("비밀번호 변경")
        self.setModal(True)
        self.setMinimumSize(420, 260)
        self.setStyleSheet(
            " ".join(
                [
                    f"QDialog {{ background: {palette['dialog_bg']}; color: {palette['dialog_text']}; }}",
                    f"QDialog QLabel {{ color: {palette['dialog_text']}; }}",
                    f"QDialog QLineEdit {{ background: {palette['bg_card']};"
                    f" border: 1px solid {palette['dialog_border']};"
                    " border-radius: 8px; padding: 6px 10px;",
                    f" color: {palette['dialog_text']}; }}",
                    f"QDialog QPushButton {{ background: {palette['accent']}; color: #0b1220;",
                    " border-radius: 10px; padding: 6px 12px; font-weight: 700; }}",
                ]
            )
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        description = QtWidgets.QLabel("현재 비밀번호와 새 비밀번호를 입력하세요.")
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QtWidgets.QFormLayout()
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        form.setFormAlignment(QtCore.Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.current_password = QtWidgets.QLineEdit()
        self.current_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.new_password = QtWidgets.QLineEdit()
        self.new_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.confirm_password = QtWidgets.QLineEdit()
        self.confirm_password.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("현재 비밀번호", self.current_password)
        form.addRow("새 비밀번호", self.new_password)
        form.addRow("비밀번호 확인", self.confirm_password)
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        cancel = QtWidgets.QPushButton("취소")
        ok = QtWidgets.QPushButton("변경")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

class NoticeWindow(QtWidgets.QWidget):
    closed = QtCore.Signal()

    def __init__(self, palette: dict, cfg: AppConfig, parent=None, preview: bool = False):
        super().__init__(parent)
        self.setObjectName("NoticeWindow")
        self._preview = preview
        if preview:
            self.setWindowFlags(QtCore.Qt.Widget)
        else:
            self.setWindowFlags(
                QtCore.Qt.Window | QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowStaysOnTopHint
            )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.setWindowTitle("AutoWake 안내")
        self.palette = palette
        self.cfg = cfg
        self._interaction_locked = False
        self._build_ui()
        self._apply_palette()
        self.update_content(cfg)
        if preview:
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            self.cfg.notice_frame_padding,
            self.cfg.notice_frame_padding,
            self.cfg.notice_frame_padding,
            self.cfg.notice_frame_padding,
        )
        self.frame = QtWidgets.QFrame()
        self.frame.setObjectName("NoticeFrame")
        frame_layout = QtWidgets.QVBoxLayout(self.frame)
        header_row = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel(DEFAULT_NOTICE_TITLE)
        self.title_label.setObjectName("NoticeTitle")
        self.close_button = QtWidgets.QPushButton("닫기")
        self.close_button.setObjectName("NoticeClose")
        self.close_button.clicked.connect(self.close)
        self.close_button.setFixedSize(120, 40)
        header_row.addWidget(self.title_label)
        header_row.addStretch()
        header_row.addWidget(self.close_button)
        frame_layout.addLayout(header_row)
        self.image_label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
        self.image_label.setObjectName("NoticeImage")
        self.body_label = QtWidgets.QLabel()
        self.body_label.setWordWrap(True)
        self.body_label.setObjectName("NoticeBody")
        self.footer_label = QtWidgets.QLabel()
        self.footer_label.setWordWrap(True)
        self.footer_label.setObjectName("NoticeFooter")
        frame_layout.addWidget(self.image_label)
        frame_layout.addWidget(self.body_label)
        frame_layout.addWidget(self.footer_label)
        layout.addWidget(self.frame)

    def _apply_palette(self) -> None:
        palette = self.palette
        frame_color = self.cfg.notice_frame_color or "#0f172a"
        qpalette = QtGui.QPalette()
        qpalette.setColor(QtGui.QPalette.Window, QtGui.QColor(frame_color))
        self.setPalette(qpalette)
        self.setStyleSheet(
            f"""
            #NoticeWindow {{
                background: {frame_color};
            }}
            #NoticeFrame {{
                background: {palette['bg_card']};
                border-radius: 16px;
                border: none;
            }}
            #NoticeClose {{
                background: {palette['accent']};
                color: #0b1220;
                font-weight: 800;
                border-radius: 10px;
                padding: 6px 16px;
                min-width: 120px;
                min-height: 40px;
            }}
            #NoticeTitle {{
                color: {palette['text_primary']};
                font-size: 18px;
                font-weight: 700;
            }}
            #NoticeBody {{
                color: {palette['text_muted']};
            }}
            #NoticeFooter {{
                color: {palette['text_muted']};
            }}
            """
        )
        self._apply_window_icon()

    def _apply_window_icon(self) -> None:
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

    def _apply_frame_style(self) -> None:
        self.frame.setStyleSheet(
            " ".join(
                [
                    f"background: {self.palette['bg_card']};",
                    "border-radius: 16px;",
                    "border: none;",
                ]
            )
        )

    def set_interaction_lock(self, locked: bool) -> None:
        if self._preview:
            return
        self._interaction_locked = locked
        if locked:
            self.setWindowModality(QtCore.Qt.ApplicationModal)
            if not (self.windowFlags() & QtCore.Qt.WindowStaysOnTopHint):
                self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        else:
            self.setWindowModality(QtCore.Qt.NonModal)
            if self.windowFlags() & QtCore.Qt.WindowStaysOnTopHint:
                self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
        if self.isVisible():
            self.show()
            self._apply_window_icon()
            if locked:
                self.raise_()
                self.activateWindow()

    def update_content(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        outer_layout: QtWidgets.QVBoxLayout = self.layout()
        if outer_layout is not None:
            padding = max(0, int(cfg.notice_frame_padding))
            outer_layout.setContentsMargins(padding, padding, padding, padding)
        self._apply_palette()
        title, body, footer = build_notice_content(cfg)
        self.title_label.setText(title)
        self.body_label.setTextFormat(QtCore.Qt.PlainText)
        self.footer_label.setTextFormat(QtCore.Qt.PlainText)
        self.body_label.setText(body)
        self.footer_label.setText(footer)
        body_font = _build_notice_font(
            cfg.notice_body_font_family,
            cfg.notice_body_font_size,
            cfg.notice_body_bold,
            cfg.notice_body_italic,
        )
        footer_font = _build_notice_font(
            cfg.notice_footer_font_family,
            cfg.notice_footer_font_size,
            cfg.notice_footer_bold,
            cfg.notice_footer_italic,
        )
        self.body_label.setFont(body_font)
        self.footer_label.setFont(footer_font)
        self.body_label.setStyleSheet(_notice_style(body_font))
        self.footer_label.setStyleSheet(_notice_style(footer_font))
        self.body_label.setAlignment(_notice_alignment(cfg.notice_body_align))
        self.footer_label.setAlignment(_notice_alignment(cfg.notice_footer_align))
        self._apply_frame_style()
        self._update_image()

    def _update_image(self) -> None:
        path = resolve_notice_image_path(self.cfg)
        height = max(20, int(self.cfg.notice_image_height))
        self.image_label.setFixedHeight(height)
        if not path:
            self.image_label.clear()
            self.image_label.show()
            return
        pixmap = QtGui.QPixmap(path)
        if pixmap.isNull():
            self.image_label.clear()
            self.image_label.show()
            return
        scaled = pixmap.scaledToHeight(height, QtCore.Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.show()

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.closed.emit()
        self.releaseMouse()
        self.releaseKeyboard()
        self.hide()
        event.ignore()

    def show_centered(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 800, 600)
        self.adjustSize()
        hint = self.sizeHint()
        min_width = 520
        min_height = 320
        preset_width, preset_height = resolve_notice_window_size(self.cfg)
        width = max(min_width, preset_width, hint.width())
        height = max(min_height, preset_height, hint.height())
        width = min(int(geometry.width() * 0.9), width)
        height = min(int(geometry.height() * 0.9), height)
        self.setGeometry(
            geometry.center().x() - width // 2,
            geometry.center().y() - height // 2,
            width,
            height,
        )
        self._apply_window_icon()
        self.show()
        self.raise_()
        self.activateWindow()
        self.set_interaction_lock(True)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self.set_interaction_lock(False)
        super().hideEvent(event)

    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        if self._interaction_locked:
            self.raise_()
            self.activateWindow()
        super().focusOutEvent(event)


class NoticePreviewWidget(QtWidgets.QWidget):
    def __init__(self, palette: dict, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.palette = palette
        self.cfg = cfg
        self.setObjectName("NoticePreview")
        self._base_size = QtCore.QSize(640, 420)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.view = QtWidgets.QGraphicsView()
        self.view.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setAlignment(QtCore.Qt.AlignCenter)
        self.view.setRenderHints(
            QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform
        )
        self.view.setViewportMargins(8, 8, 8, 8)
        self.scene = QtWidgets.QGraphicsScene(self.view)
        self.view.setScene(self.scene)
        layout.addWidget(self.view)
        self.notice = NoticeWindow(self.palette, self.cfg, preview=True)
        self.notice.resize(self._base_size)
        self.proxy = self.scene.addWidget(self.notice)
        self._apply_palette()
        self.apply_config(cfg)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._sync_scale)

    def _apply_palette(self) -> None:
        palette = self.palette
        self.view.setStyleSheet(
            f"""
            #NoticePreview {{
                background: {palette['bg']};
                border-radius: 14px;
                border: none;
            }}
            """
        )
        self.view.setBackgroundBrush(QtGui.QColor(palette["bg"]))

    def apply_config(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.notice.palette = self.palette
        self.notice.update_content(cfg)
        self.notice.adjustSize()
        size_hint = self.notice.sizeHint()
        preset_width, preset_height = resolve_notice_window_size(cfg)
        width = max(self._base_size.width(), size_hint.width(), preset_width)
        height = max(self._base_size.height(), size_hint.height(), preset_height)
        self.notice.resize(QtCore.QSize(width, height))
        self.notice.show()
        self._sync_scale()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_scale()

    def _sync_scale(self) -> None:
        if not self.proxy:
            return
        rect = self.scene.itemsBoundingRect()
        if rect.isNull():
            return
        rect.adjust(-8, -8, 8, 8)
        self.scene.setSceneRect(rect)
        self.view.resetTransform()
        self.view.fitInView(rect, QtCore.Qt.KeepAspectRatio)


class NoticeConfigDialog(QtWidgets.QDialog):
    def __init__(self, palette: dict, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("안내 팝업 구성")
        self.setModal(True)
        self.setMinimumSize(1180, 820)
        self.palette = palette
        self.cfg = cfg
        self._build_ui()
        self._load_config(cfg)
        self._connect_signals()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)

        preview_panel = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(12)
        preview_title = QtWidgets.QLabel("안내 팝업 미리보기")
        preview_title.setObjectName("CardTitle")
        preview_layout.addWidget(preview_title)
        self.preview_size_label = QtWidgets.QLabel("")
        self.preview_size_label.setObjectName("CardSubtitle")
        preview_layout.addWidget(self.preview_size_label)
        self.preview = NoticePreviewWidget(self.palette, self.cfg)
        self.preview.setMinimumWidth(460)
        preview_layout.addWidget(self.preview, 1)
        control_panel = QtWidgets.QWidget()
        control_layout = QtWidgets.QVBoxLayout(control_panel)
        control_layout.setContentsMargins(12, 12, 12, 12)
        control_layout.setSpacing(16)
        control_panel.setStyleSheet(
            " ".join(
                [
                    f"QWidget {{ background: {self.palette['dialog_bg']};",
                    f"color: {self.palette['dialog_text']}; }}",
                    f"QLabel, QCheckBox, QRadioButton {{ color: {self.palette['dialog_text']};",
                    "font-size: 14px; }}",
                    f"QGroupBox {{ background: {self.palette['dialog_bg']};",
                    f"border: 2px solid {self.palette['dialog_border']};",
                    "border-radius: 12px; margin-top: 10px; padding: 8px; }}",
                    "QGroupBox::title { subcontrol-origin: margin; left: 12px;",
                    "padding: 0 6px; font-size: 14px; font-weight: 700; }",
                    f"QCheckBox::indicator {{ width: 16px; height: 16px; }}",
                    f"QCheckBox::indicator:unchecked {{ border: 1px solid {self.palette['dialog_border']};",
                    f"background: {self.palette['bg_card']}; border-radius: 4px; }}",
                    f"QCheckBox::indicator:checked {{ border: 1px solid {self.palette['accent']};",
                    f"background: {self.palette['accent']}; border-radius: 4px; }}",
                    f"QComboBox {{ background: {self.palette['bg_card']};",
                    f"border: 1px solid {self.palette['accent']};",
                    f"color: {self.palette['dialog_text']}; }}",
                    f"QComboBox::drop-down {{ border: none; background: {self.palette['accent']}; }}",
                    f"QComboBox::down-arrow {{ image: none; }}",
                    f"QComboBox::down-arrow {{ border-left: 6px solid transparent;",
                    f"border-right: 6px solid transparent;",
                    f"border-top: 8px solid {self.palette['dialog_bg']}; }}",
                    f"QSpinBox, QDoubleSpinBox {{ background: {self.palette['bg_card']};",
                    f"border: 1px solid {self.palette['accent']};",
                    f"color: {self.palette['dialog_text']}; }}",
                    f"QSpinBox::up-button, QSpinBox::down-button,",
                    f"QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{",
                    f"border: none; background: {self.palette['accent']}; width: 18px; }}",
                    f"QSpinBox::up-arrow, QSpinBox::down-arrow,",
                    f"QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{",
                    f"width: 0; height: 0; border-left: 5px solid transparent;",
                    f"border-right: 5px solid transparent; }}",
                    f"QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{",
                    f"border-bottom: 7px solid {self.palette['dialog_bg']}; }}",
                    f"QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{",
                    f"border-top: 7px solid {self.palette['dialog_bg']}; }}",
                ]
            )
        )
        general_group = QtWidgets.QGroupBox("기본 설정")
        general_layout = QtWidgets.QFormLayout(general_group)
        general_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        general_layout.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        general_layout.setHorizontalSpacing(12)
        general_layout.setVerticalSpacing(10)
        self.notice_title = QtWidgets.QLineEdit()
        general_layout.addRow("제목", self.notice_title)

        self.image_mode = QtWidgets.QComboBox()
        self.image_mode.addItem("기본 이미지", "bundled")
        self.image_mode.addItem("사용자 지정", "path")
        self.image_mode.addItem("없음", "none")
        general_layout.addRow("상단 삽입 이미지", self.image_mode)

        self.bundled_image = QtWidgets.QComboBox()
        for name in NOTICE_BUNDLED_IMAGES:
            self.bundled_image.addItem(NOTICE_BUNDLED_LABELS.get(name, name), name)
        general_layout.addRow("기본 이미지 선택", self.bundled_image)

        path_row = QtWidgets.QWidget()
        path_layout = QtWidgets.QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.image_path = QtWidgets.QLineEdit()
        self.image_path_browse = QtWidgets.QPushButton("찾기")
        self.image_path_browse.clicked.connect(self._browse_image)
        path_layout.addWidget(self.image_path)
        path_layout.addWidget(self.image_path_browse)
        general_layout.addRow("이미지 경로", path_row)

        self.image_height = StepperInput()
        self.image_height.setRange(20, 400)
        self.image_height.setSingleStep(5)
        self.image_height.setDecimals(0)
        general_layout.addRow("이미지 높이(px)", self.image_height)

        control_layout.addWidget(general_group)

        body_group = QtWidgets.QGroupBox("본문")
        body_layout = QtWidgets.QVBoxLayout(body_group)
        body_layout.setSpacing(10)
        self.body_text = QtWidgets.QTextEdit()
        self.body_text.setMinimumHeight(120)
        body_layout.addWidget(self.body_text)
        body_row = QtWidgets.QGridLayout()
        self.body_font_size = StepperInput()
        self.body_font_size.setRange(9, 28)
        self.body_font_size.setSingleStep(1)
        self.body_font_size.setDecimals(0)
        self.body_bold = QtWidgets.QCheckBox("굵게")
        self.body_italic = QtWidgets.QCheckBox("기울임")
        self.body_font_family = QtWidgets.QComboBox()
        self.body_font_family.addItems(NOTICE_FONT_FAMILIES)
        self.body_font_family.setEditable(False)
        self.body_align = QtWidgets.QComboBox()
        self.body_align.addItem("왼쪽", "left")
        self.body_align.addItem("가운데", "center")
        self.body_align.addItem("오른쪽", "right")
        font_row = QtWidgets.QHBoxLayout()
        font_row.addWidget(QtWidgets.QLabel("글씨체"))
        font_row.addWidget(self.body_font_family)
        body_row.addWidget(QtWidgets.QLabel("글씨 크기"), 0, 0)
        body_row.addWidget(self.body_font_size, 0, 1)
        body_row.addWidget(self.body_bold, 0, 2)
        body_row.addWidget(self.body_italic, 0, 3)
        body_row.addWidget(QtWidgets.QLabel("정렬"), 0, 4)
        body_row.addWidget(self.body_align, 0, 5)
        body_row.setColumnStretch(6, 1)
        body_layout.addLayout(body_row)
        body_layout.addLayout(font_row)
        control_layout.addWidget(body_group)

        footer_group = QtWidgets.QGroupBox("추가 내용")
        footer_layout = QtWidgets.QVBoxLayout(footer_group)
        footer_layout.setSpacing(10)
        self.footer_text = QtWidgets.QTextEdit()
        self.footer_text.setMinimumHeight(120)
        footer_layout.addWidget(self.footer_text)
        footer_row = QtWidgets.QGridLayout()
        self.footer_font_size = StepperInput()
        self.footer_font_size.setRange(9, 24)
        self.footer_font_size.setSingleStep(1)
        self.footer_font_size.setDecimals(0)
        self.footer_bold = QtWidgets.QCheckBox("굵게")
        self.footer_italic = QtWidgets.QCheckBox("기울임")
        self.footer_font_family = QtWidgets.QComboBox()
        self.footer_font_family.addItems(NOTICE_FONT_FAMILIES)
        self.footer_font_family.setEditable(False)
        self.footer_align = QtWidgets.QComboBox()
        self.footer_align.addItem("왼쪽", "left")
        self.footer_align.addItem("가운데", "center")
        self.footer_align.addItem("오른쪽", "right")
        footer_font_row = QtWidgets.QHBoxLayout()
        footer_font_row.addWidget(QtWidgets.QLabel("글씨체"))
        footer_font_row.addWidget(self.footer_font_family)
        footer_row.addWidget(QtWidgets.QLabel("글씨 크기"), 0, 0)
        footer_row.addWidget(self.footer_font_size, 0, 1)
        footer_row.addWidget(self.footer_bold, 0, 2)
        footer_row.addWidget(self.footer_italic, 0, 3)
        footer_row.addWidget(QtWidgets.QLabel("정렬"), 0, 4)
        footer_row.addWidget(self.footer_align, 0, 5)
        footer_row.setColumnStretch(6, 1)
        footer_layout.addLayout(footer_row)
        footer_layout.addLayout(footer_font_row)
        control_layout.addWidget(footer_group)

        frame_group = QtWidgets.QGroupBox("프레임/재노출")
        frame_layout = QtWidgets.QVBoxLayout(frame_group)
        frame_layout.setSpacing(10)
        frame_row = QtWidgets.QHBoxLayout()
        self.frame_color_button = QtWidgets.QPushButton("여백 색상")
        self.frame_color_button.clicked.connect(self._pick_frame_color)
        self.frame_padding = StepperInput()
        self.frame_padding.setRange(0, 80)
        self.frame_padding.setSingleStep(2)
        self.frame_padding.setDecimals(0)
        frame_row.addWidget(self.frame_color_button)
        frame_row.addSpacing(12)
        frame_row.addWidget(QtWidgets.QLabel("여백 폭"))
        frame_row.addWidget(self.frame_padding)
        frame_row.addStretch()
        frame_layout.addLayout(frame_row)

        repeat_row = QtWidgets.QHBoxLayout()
        self.notice_repeat_enabled = QtWidgets.QCheckBox("닫힌 후 재노출")
        self.notice_repeat_interval = StepperInput()
        self.notice_repeat_interval.setRange(1, 240)
        self.notice_repeat_interval.setSingleStep(1)
        self.notice_repeat_interval.setDecimals(0)
        repeat_row.addWidget(self.notice_repeat_enabled)
        repeat_row.addSpacing(12)
        repeat_row.addWidget(QtWidgets.QLabel("경과 시간(분)"))
        repeat_row.addWidget(self.notice_repeat_interval)
        repeat_row.addStretch()
        frame_layout.addLayout(repeat_row)
        self.notice_repeat_hint = QtWidgets.QLabel(
            "스크린 세이버 사용 시 재노출 옵션은 비활성화됩니다."
        )
        self.notice_repeat_hint.setObjectName("CardSubtitle")
        self.notice_repeat_hint.setWordWrap(True)
        frame_layout.addWidget(self.notice_repeat_hint)

        control_layout.addWidget(frame_group)

        window_group = QtWidgets.QGroupBox("창 크기")
        window_layout = QtWidgets.QFormLayout(window_group)
        window_layout.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        window_layout.setHorizontalSpacing(12)
        window_layout.setVerticalSpacing(10)
        self.notice_size_preset = QtWidgets.QComboBox()
        for key, (label, _size) in NOTICE_WINDOW_PRESETS.items():
            self.notice_size_preset.addItem(label, key)
        self.notice_window_width = StepperInput()
        self.notice_window_width.setRange(360, 1400)
        self.notice_window_width.setSingleStep(20)
        self.notice_window_width.setDecimals(0)
        self.notice_window_height = StepperInput()
        self.notice_window_height.setRange(240, 1000)
        self.notice_window_height.setSingleStep(20)
        self.notice_window_height.setDecimals(0)
        window_layout.addRow("크기 프리셋", self.notice_size_preset)
        window_layout.addRow("너비(px)", self.notice_window_width)
        window_layout.addRow("높이(px)", self.notice_window_height)
        control_layout.addWidget(window_group)
        control_layout.addStretch()

        button_row = QtWidgets.QHBoxLayout()
        self.export_button = QtWidgets.QPushButton("내보내기")
        self.import_button = QtWidgets.QPushButton("불러오기")
        self.save_button = QtWidgets.QPushButton("저장")
        self.cancel_button = QtWidgets.QPushButton("취소")
        self.export_button.clicked.connect(self._export_config)
        self.import_button.clicked.connect(self._import_config)
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.export_button)
        button_row.addWidget(self.import_button)
        button_row.addStretch()
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        control_layout.addLayout(button_row)

        control_scroll = QtWidgets.QScrollArea()
        control_scroll.setWidgetResizable(True)
        control_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        control_scroll.setWidget(control_panel)

        controls_wrapper = QtWidgets.QWidget()
        controls_layout = QtWidgets.QVBoxLayout(controls_wrapper)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)
        controls_layout.addWidget(control_scroll)
        controls_wrapper.setMinimumWidth(560)

        self.splitter.addWidget(controls_wrapper)
        self.splitter.addWidget(preview_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([560, 620])

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._sync_splitter)

    def _sync_splitter(self) -> None:
        if hasattr(self, "splitter"):
            self.splitter.setSizes([560, 620])
        if hasattr(self, "preview"):
            self.preview._sync_scale()

    def _connect_signals(self) -> None:
        self.notice_title.textChanged.connect(self._update_preview)
        self.image_mode.currentIndexChanged.connect(self._handle_image_mode)
        self.bundled_image.currentIndexChanged.connect(self._update_preview)
        self.image_path.textChanged.connect(self._update_preview)
        self.image_height.valueChanged.connect(self._update_preview)
        self.body_text.textChanged.connect(self._update_preview)
        self.body_font_size.valueChanged.connect(self._update_preview)
        self.body_bold.stateChanged.connect(self._update_preview)
        self.body_italic.stateChanged.connect(self._update_preview)
        self.body_font_family.currentIndexChanged.connect(self._update_preview)
        self.body_align.currentIndexChanged.connect(self._update_preview)
        self.footer_text.textChanged.connect(self._update_preview)
        self.footer_font_size.valueChanged.connect(self._update_preview)
        self.footer_bold.stateChanged.connect(self._update_preview)
        self.footer_italic.stateChanged.connect(self._update_preview)
        self.footer_font_family.currentIndexChanged.connect(self._update_preview)
        self.footer_align.currentIndexChanged.connect(self._update_preview)
        self.frame_padding.valueChanged.connect(self._update_preview)
        self.notice_repeat_enabled.stateChanged.connect(self._update_preview)
        self.notice_repeat_interval.valueChanged.connect(self._update_preview)
        self.notice_size_preset.currentIndexChanged.connect(self._apply_window_preset)
        self.notice_window_width.valueChanged.connect(self._update_preview)
        self.notice_window_height.valueChanged.connect(self._update_preview)

    def _load_config(self, cfg: AppConfig) -> None:
        self.notice_title.setText(cfg.notice_title)
        mode = (cfg.notice_image_mode or DEFAULT_NOTICE_IMAGE_MODE).lower()
        index = self.image_mode.findData(mode)
        if index >= 0:
            self.image_mode.setCurrentIndex(index)
        bundled_index = self.bundled_image.findData(cfg.notice_bundled_image)
        if bundled_index >= 0:
            self.bundled_image.setCurrentIndex(bundled_index)
        self.image_path.setText(cfg.notice_image_path)
        self.image_height.setValue(float(cfg.notice_image_height))
        self.body_text.setPlainText(cfg.notice_body)
        self.body_font_size.setValue(int(cfg.notice_body_font_size))
        self.body_bold.setChecked(bool(cfg.notice_body_bold))
        self.body_italic.setChecked(bool(cfg.notice_body_italic))
        body_font_index = self.body_font_family.findText(cfg.notice_body_font_family)
        if body_font_index >= 0:
            self.body_font_family.setCurrentIndex(body_font_index)
        body_align_index = self.body_align.findData(cfg.notice_body_align)
        if body_align_index >= 0:
            self.body_align.setCurrentIndex(body_align_index)
        self.footer_text.setPlainText(cfg.notice_footer)
        self.footer_font_size.setValue(int(cfg.notice_footer_font_size))
        self.footer_bold.setChecked(bool(cfg.notice_footer_bold))
        self.footer_italic.setChecked(bool(cfg.notice_footer_italic))
        footer_font_index = self.footer_font_family.findText(cfg.notice_footer_font_family)
        if footer_font_index >= 0:
            self.footer_font_family.setCurrentIndex(footer_font_index)
        footer_align_index = self.footer_align.findData(cfg.notice_footer_align)
        if footer_align_index >= 0:
            self.footer_align.setCurrentIndex(footer_align_index)
        self.frame_padding.setValue(float(cfg.notice_frame_padding))
        self._update_frame_color_button(cfg.notice_frame_color)
        self.notice_repeat_enabled.setChecked(bool(cfg.notice_repeat_enabled))
        self.notice_repeat_interval.setValue(float(cfg.notice_repeat_interval_min))
        preset_key = (cfg.notice_window_preset or "auto").lower()
        preset_index = self.notice_size_preset.findData(preset_key)
        if preset_index >= 0:
            self.notice_size_preset.setCurrentIndex(preset_index)
        if cfg.notice_window_width > 0:
            self.notice_window_width.setValue(float(cfg.notice_window_width))
        if cfg.notice_window_height > 0:
            self.notice_window_height.setValue(float(cfg.notice_window_height))
        saver_enabled = bool(cfg.saver_enabled)
        self.notice_repeat_enabled.setEnabled(not saver_enabled)
        self.notice_repeat_interval.setEnabled(not saver_enabled)
        self.notice_repeat_hint.setVisible(saver_enabled)
        self._handle_image_mode()
        self._apply_window_preset()

    def _handle_image_mode(self) -> None:
        mode = self.image_mode.currentData()
        is_bundled = mode == "bundled"
        is_path = mode == "path"
        self.bundled_image.setVisible(is_bundled)
        self.image_path.setEnabled(is_path)
        self.image_path_browse.setEnabled(is_path)
        self._update_preview()

    def _frame_color_value(self) -> str:
        return getattr(self, "_frame_color_value_hex", "") or ""

    def _apply_window_preset(self) -> None:
        preset_key = self.notice_size_preset.currentData() or "auto"
        _, size = NOTICE_WINDOW_PRESETS.get(preset_key, NOTICE_WINDOW_PRESETS["auto"])
        if preset_key == "custom":
            self.notice_window_width.setEnabled(True)
            self.notice_window_height.setEnabled(True)
        elif preset_key == "auto":
            self.notice_window_width.setEnabled(False)
            self.notice_window_height.setEnabled(False)
            self.notice_window_width.setValue(0)
            self.notice_window_height.setValue(0)
        else:
            self.notice_window_width.setEnabled(False)
            self.notice_window_height.setEnabled(False)
            self.notice_window_width.setValue(size[0])
            self.notice_window_height.setValue(size[1])
        self._update_preview()

    def _update_frame_color_button(self, color_hex: str) -> None:
        if not color_hex:
            color_hex = "#0f172a"
        self._frame_color_value_hex = color_hex
        self.frame_color_button.setStyleSheet(
            " ".join(
                [
                    f"background: {color_hex};",
                    "color: #0b1220;",
                    "border-radius: 10px;",
                    "padding: 6px 12px;",
                    "font-weight: 700;",
                ]
            )
        )

    def _pick_frame_color(self) -> None:
        current = self._frame_color_value() or "#0f172a"
        dialog = QtWidgets.QColorDialog(QtGui.QColor(current), self)
        dialog.setOption(QtWidgets.QColorDialog.ShowAlphaChannel, False)
        dialog.setOption(QtWidgets.QColorDialog.DontUseNativeDialog, True)
        dialog.currentColorChanged.connect(
            lambda color: self._update_frame_color_button(color.name())
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self._update_frame_color_button(dialog.currentColor().name())
            self._update_preview()

    def _browse_image(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "이미지 선택",
            self.image_path.text() or os.path.expanduser("~"),
            "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if path:
            self.image_path.setText(path)

    def _export_config(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "안내 팝업 내보내기",
            os.path.expanduser("~"),
            "JSON 파일 (*.json)",
        )
        if not path:
            return
        data = self._build_notice_config()
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            log(f"NOTICE export error: {exc}")

    def _import_config(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "안내 팝업 불러오기",
            os.path.expanduser("~"),
            "JSON 파일 (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            log(f"NOTICE import error: {exc}")
            return
        cfg = replace(
            self.cfg,
            notice_title=str(data.get("notice_title", DEFAULT_NOTICE_TITLE)),
            notice_body=str(data.get("notice_body", DEFAULT_NOTICE_BODY)),
            notice_footer=str(data.get("notice_footer", DEFAULT_NOTICE_FOOTER)),
            notice_body_font_size=int(data.get("notice_body_font_size", 13)),
            notice_body_bold=bool(data.get("notice_body_bold", False)),
            notice_body_italic=bool(data.get("notice_body_italic", False)),
            notice_body_align=str(data.get("notice_body_align", "left")),
            notice_body_font_family=str(data.get("notice_body_font_family", "Noto Sans KR")),
            notice_footer_font_size=int(data.get("notice_footer_font_size", 12)),
            notice_footer_bold=bool(data.get("notice_footer_bold", False)),
            notice_footer_italic=bool(data.get("notice_footer_italic", False)),
            notice_footer_align=str(data.get("notice_footer_align", "left")),
            notice_footer_font_family=str(data.get("notice_footer_font_family", "Noto Sans KR")),
            notice_frame_color=str(data.get("notice_frame_color", "#0f172a")),
            notice_frame_padding=int(data.get("notice_frame_padding", 24)),
            notice_repeat_enabled=bool(data.get("notice_repeat_enabled", False)),
            notice_repeat_interval_min=int(data.get("notice_repeat_interval_min", 30)),
            notice_image_mode=str(data.get("notice_image_mode", DEFAULT_NOTICE_IMAGE_MODE)),
            notice_image_path=str(data.get("notice_image_path", DEFAULT_NOTICE_IMAGE_PATH)),
            notice_bundled_image=str(
                data.get("notice_bundled_image", DEFAULT_NOTICE_BUNDLED_IMAGE)
            ),
            notice_image_height=int(data.get("notice_image_height", DEFAULT_NOTICE_IMAGE_HEIGHT)),
        )
        self._load_config(cfg)

    def _build_notice_config(self) -> dict:
        return {
            "notice_title": self.notice_title.text().strip() or DEFAULT_NOTICE_TITLE,
            "notice_body": _normalize_notice_text(
                self.body_text.toPlainText(), DEFAULT_NOTICE_BODY
            ),
            "notice_footer": _normalize_notice_text(
                self.footer_text.toPlainText(), DEFAULT_NOTICE_FOOTER
            ),
            "notice_body_font_size": int(self.body_font_size.value()),
            "notice_body_bold": bool(self.body_bold.isChecked()),
            "notice_body_italic": bool(self.body_italic.isChecked()),
            "notice_body_align": str(self.body_align.currentData()),
            "notice_body_font_family": self.body_font_family.currentText(),
            "notice_footer_font_size": int(self.footer_font_size.value()),
            "notice_footer_bold": bool(self.footer_bold.isChecked()),
            "notice_footer_italic": bool(self.footer_italic.isChecked()),
            "notice_footer_align": str(self.footer_align.currentData()),
            "notice_footer_font_family": self.footer_font_family.currentText(),
            "notice_frame_color": self._frame_color_value(),
            "notice_frame_padding": int(self.frame_padding.value()),
            "notice_repeat_enabled": bool(self.notice_repeat_enabled.isChecked()),
            "notice_repeat_interval_min": int(self.notice_repeat_interval.value()),
            "notice_window_width": int(self.notice_window_width.value()),
            "notice_window_height": int(self.notice_window_height.value()),
            "notice_window_preset": str(self.notice_size_preset.currentData() or "auto"),
            "notice_image_mode": str(self.image_mode.currentData()),
            "notice_image_path": self.image_path.text().strip(),
            "notice_bundled_image": str(self.bundled_image.currentData()),
            "notice_image_height": int(self.image_height.value()),
        }

    def _update_preview(self) -> None:
        config = self._build_notice_config()
        preview_cfg = replace(
            self.cfg,
            notice_title=config["notice_title"],
            notice_body=config["notice_body"],
            notice_footer=config["notice_footer"],
            notice_body_font_size=config["notice_body_font_size"],
            notice_body_bold=config["notice_body_bold"],
            notice_body_italic=config["notice_body_italic"],
            notice_body_align=config["notice_body_align"],
            notice_body_font_family=config["notice_body_font_family"],
            notice_footer_font_size=config["notice_footer_font_size"],
            notice_footer_bold=config["notice_footer_bold"],
            notice_footer_italic=config["notice_footer_italic"],
            notice_footer_align=config["notice_footer_align"],
            notice_footer_font_family=config["notice_footer_font_family"],
            notice_frame_color=config["notice_frame_color"],
            notice_frame_padding=config["notice_frame_padding"],
            notice_repeat_enabled=config["notice_repeat_enabled"],
            notice_repeat_interval_min=config["notice_repeat_interval_min"],
            notice_window_width=config["notice_window_width"],
            notice_window_height=config["notice_window_height"],
            notice_window_preset=config["notice_window_preset"],
            notice_image_mode=config["notice_image_mode"],
            notice_image_path=config["notice_image_path"],
            notice_bundled_image=config["notice_bundled_image"],
            notice_image_height=config["notice_image_height"],
        )
        self.preview.apply_config(preview_cfg)
        width, height = resolve_notice_window_size(preview_cfg)
        if width > 0 and height > 0:
            self.preview_size_label.setText(f"현재 크기: {width} x {height}px")
        else:
            self.preview_size_label.setText("현재 크기: 자동")

    def get_notice_config(self) -> dict:
        return self._build_notice_config()


class SaverWindow(QtWidgets.QWidget):
    def __init__(self, cfg: AppConfig, palette: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.palette = palette
        self.label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

    def load_pixmap(self) -> QtGui.QPixmap:
        mode = (self.cfg.saver_image_mode or "path").lower()
        if mode == "generated":
            return self._build_fallback_pixmap()
        if mode == "bundled":
            path = resource_path(DEFAULT_BUNDLED_IMAGE)
        else:
            path = self.cfg.image_path
        if path and os.path.exists(path):
            pixmap = QtGui.QPixmap(path)
            if not pixmap.isNull():
                return pixmap
        return self._build_fallback_pixmap()

    def _build_fallback_pixmap(self) -> QtGui.QPixmap:
        width, height = 1600, 900
        pixmap = QtGui.QPixmap(width, height)
        pixmap.fill(QtGui.QColor(self.palette["bg_dark"]))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QColor(self.palette["text_primary"]))
        title_font = QtGui.QFont("Segoe UI", 42, QtGui.QFont.Bold)
        subtitle_font = QtGui.QFont("Segoe UI", 22)
        detail_font = QtGui.QFont("Segoe UI", 18)
        painter.setFont(title_font)
        painter.drawText(QtCore.QPoint(120, 160), "AutoWake")
        painter.setFont(subtitle_font)
        painter.drawText(QtCore.QPoint(120, 230), "자동 생성 안내 이미지")
        painter.setFont(detail_font)
        painter.setPen(QtGui.QColor(self.palette["text_muted"]))
        painter.drawText(QtCore.QPoint(120, 280), "참고자료실 전용 도서 검색 PC입니다.")
        painter.drawText(QtCore.QPoint(120, 320), "사용해 주셔서 감사합니다.")
        painter.end()
        return pixmap

    def refresh(self):
        pixmap = self.load_pixmap()
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            mode = (self.cfg.saver_display_mode or "full").lower()
            geometry = screen.availableGeometry() if mode == "workarea" else screen.geometry()
            target_size = geometry.size()
            if mode == "workarea":
                scaled = pixmap.scaled(
                    target_size, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation
                )
                if scaled.size() != target_size:
                    x = max(0, (scaled.width() - target_size.width()) // 2)
                    y = max(0, (scaled.height() - target_size.height()) // 2)
                    scaled = scaled.copy(x, y, target_size.width(), target_size.height())
            else:
                scaled = pixmap.scaled(
                    target_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
                )
        else:
            scaled = pixmap
        self.label.setPixmap(scaled)

    def show_fullscreen(self):
        self.refresh()
        if (self.cfg.saver_display_mode or "full") == "workarea":
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen:
                geometry = screen.availableGeometry()
                self.setGeometry(geometry)
                self.show()
                return
        self.showFullScreen()


class ProcessManager:
    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}

    def start(self, mode: str):
        if mode in self.processes and self.processes[mode].poll() is None:
            return
        if getattr(sys, "frozen", False):
            args = [sys.executable, "--mode", mode]
        else:
            args = [sys.executable, os.path.abspath(__file__), "--mode", mode]
        creationflags = (
            subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self.processes[mode] = proc
        log(f"Spawned worker: {mode} ({' '.join(args)})")

    def stop(self, mode: str):
        proc = self.processes.get(mode)
        if not proc:
            return
        if proc.poll() is None:
            proc.terminate()
        self.processes.pop(mode, None)

    def stop_all(self):
        for mode in list(self.processes.keys()):
            self.stop(mode)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self._mutex = single_instance_or_exit()
        self.cfg = load_config()
        self.process_manager = ProcessManager()
        self.is_running = False
        self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
        self.tray_icon: Optional[QtWidgets.QSystemTrayIcon] = None
        self.tray_menu: Optional[QtWidgets.QMenu] = None
        self.action_start: Optional[QtGui.QAction] = None
        self.action_stop: Optional[QtGui.QAction] = None
        self.action_settings: Optional[QtGui.QAction] = None
        self.action_quit: Optional[QtGui.QAction] = None
        self._password_dialog: Optional[PasswordDialog] = None
        self._opening_settings = False
        self._raising_window = False
        self._ui_active = False
        self.notice_config: dict[str, object] = {}
        write_notice_state(self.cfg.work_dir, ui_active=0.0)
        self._build_ui()
        self._apply_palette()
        self._loading = False
        self._load_config_to_ui()
        self._connect_autosave()
        self._setup_tray()
        self._ensure_default_password()

    def _apply_palette(self):
        self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
        palette = self.palette
        stylesheet = f"""
            QMainWindow {{ background: {palette['bg']}; }}
            QLabel {{ color: {palette['text_primary']}; font-family: 'Noto Sans KR', 'Malgun Gothic', 'Segoe UI', sans-serif; font-size: 13px; font-weight: 500; }}
            #TopBar {{
                background: {palette['topbar']};
                border-radius: 14px;
                border: none;
            }}
            #TopTitle {{ font-size: 20px; font-weight: 700; }}
            #StatePill {{
                background: {palette['bg_card_alt']};
                border: 1px solid {palette['border']};
                padding: 4px 10px;
                border-radius: 12px;
                font-weight: 700;
                font-size: 13px;
                color: {palette['text_primary']};
            }}
            #FancyCard {{
                background: {palette['bg_card']};
                border-radius: 14px;
                border: 1px solid {palette['border']};
            }}
            #CardTitle {{ font-size: 15px; font-weight: 700; }}
            #CardSubtitle {{ color: {palette['text_muted']}; font-size: 12px; font-weight: 500; }}
            #FormLabel {{ color: {palette['accent']}; font-size: 13px; font-weight: 600; }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                background: {palette['bg_card_alt']};
                border: 1px solid {palette['border']};
                padding: 6px 10px;
                border-radius: 8px;
                color: {palette['text_primary']};
                font-size: 13px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QPushButton {{
                background: {palette['accent']};
                border-radius: 10px;
                padding: 8px 14px;
                color: #0b1220;
                font-weight: 700;
                font-size: 14px;
            }}
            QPushButton:focus {{ outline: none; }}
            QPushButton:hover {{ background: {palette['accent_soft']}; }}
            QPushButton:pressed {{
                background: {palette['accent_dark']};
                color: #f8fafc;
            }}
            QPushButton:disabled {{
                background: {palette['accent_dark']};
                color: #0b1220;
            }}
            QPushButton#GhostButton {{
                background: {palette['accent']};
                color: #0b1220;
            }}
            QPushButton#ModeButton:focus {{ outline: none; }}
            QPushButton#ModeButton {{
                background: {palette['bg_card_alt']};
                color: {palette['text_primary']};
                border: 1px solid {palette['border']};
                padding: 6px 10px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#ModeButton:checked {{
                background: {palette['accent']};
                color: #0b1220;
            }}
            QPushButton#ModeButton:hover {{
                background: {palette['accent_soft']};
                color: #0b1220;
            }}
            QPushButton#ModeButton:pressed {{
                background: {palette['accent_dark']};
                color: #f8fafc;
            }}
            QPushButton#StepperButton {{
                background: {palette['bg_card_alt']};
                color: {palette['text_primary']};
                border: 1px solid {palette['border']};
                border-radius: 10px;
                min-width: 28px;
                min-height: 28px;
                padding: 0px;
                font-size: 16px;
                font-weight: 800;
            }}
            QPushButton#StepperButton:hover {{
                background: {palette['accent_soft']};
                color: #0b1220;
            }}
            QPushButton#StepperButton:pressed {{
                background: {palette['accent_dark']};
                color: #f8fafc;
            }}
            QPushButton#ThemeColorButton {{
                background: {palette['accent']};
                color: #0b1220;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }}
            QPushButton#ThemeColorButton:hover {{ background: {palette['accent_soft']}; }}
            QPushButton#ThemeColorButton:pressed {{
                background: {palette['accent_dark']};
                color: #f8fafc;
            }}
            QPushButton#StartButton {{
                background: {palette['accent']};
                color: #0b1220;
            }}
            QPushButton#StartButton:disabled {{
                background: {palette['bg_dark']};
                color: #f8fafc;
            }}
            QPushButton#StopButton {{
                background: #f97316;
                color: #fff7ed;
            }}
            QPushButton#StopButton:disabled {{
                background: {palette['bg_dark']};
                color: #f8fafc;
            }}
            #NoticeFrame {{
                background: {palette['bg_card']};
                border-radius: 16px;
                border: 1px solid {palette['border']};
            }}
            #NoticeTitle {{ font-size: 18px; font-weight: 700; }}
            #NoticeBody, #NoticeFooter {{ color: {palette['text_muted']}; }}
            QDialog {{
                background: {palette['dialog_bg']};
                color: {palette['dialog_text']};
            }}
            QDialog QLabel {{
                color: {palette['dialog_text']};
            }}
            QDialog QLineEdit {{
                background: {palette['bg_card']};
                border: 1px solid {palette['dialog_border']};
                border-radius: 8px;
                padding: 6px 10px;
                color: {palette['dialog_text']};
            }}
            QDialog QPushButton {{
                background: {palette['accent']};
                color: #0b1220;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }}
            QMessageBox {{
                background: {palette['dialog_bg']};
                color: {palette['dialog_text']};
            }}
            QMessageBox QLabel {{
                color: {palette['dialog_text']};
            }}
            QMessageBox QPushButton {{
                background: {palette['accent']};
                color: #0b1220;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 700;
            }}
            QTabWidget::pane {{
                border: none;
                border-radius: 12px;
                background: {palette['bg_card']};
                margin-top: 14px;
            }}
            QTabWidget::tab-bar {{
                top: 10px;
                left: 32px;
            }}
            QTabWidget::tab-bar, QTabBar::tab-bar {{
                border: none;
                background: transparent;
            }}
            QTabWidget::pane, QTabWidget::tab-bar {{
                border-top: none;
            }}
            QTabBar::base {{
                border: none;
                background: transparent;
            }}
            QTabBar::scroller {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab:!selected {{
                border-bottom: none;
            }}
            QTabBar::tab {{
                background: {palette['tab_bg']};
                color: {palette['text_primary']};
                padding: 6px 12px;
                margin-right: 6px;
                margin-bottom: 0px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border: none;
                font-size: 13px;
                font-weight: 600;
            }}
            QTabBar::tab:focus {{ outline: none; }}
            QTabBar::tab:hover {{ background: {palette['accent_soft']}; color: #0b1220; }}
            QTabBar::tab:selected {{
                background: {palette['tab_active']};
                color: {palette['text_primary']};
            }}
        """
        self.setStyleSheet(stylesheet)
        if self.tray_icon:
            self.tray_icon.setIcon(self._build_tray_icon())
        for toggle in getattr(self, "_toggles", []):
            toggle.set_palette(self.palette)
        if hasattr(self, "accent_color_button"):
            self._update_accent_color_button(self.cfg.accent_color or self.palette["accent"])
        self._update_run_state_labels()
        self._apply_dialog_palette()

    def _apply_dialog_palette(self):
        palette = self.palette
        dialog_style = (
            f"QDialog {{ background: {palette['dialog_bg']}; color: {palette['dialog_text']}; }}"
            f" QDialog QLabel {{ color: {palette['dialog_text']}; }}"
            f" QDialog QLineEdit {{ background: {palette['bg_card']}; border: 1px solid {palette['dialog_border']};"
            f" border-radius: 8px; padding: 6px 10px; color: {palette['dialog_text']}; }}"
            f" QDialog QPushButton {{ background: {palette['accent']}; color: #0b1220; border-radius: 10px;"
            f" padding: 6px 12px; font-weight: 700; }}"
            f" QMessageBox {{ background: {palette['dialog_bg']}; color: {palette['dialog_text']}; }}"
            f" QMessageBox QLabel {{ color: {palette['dialog_text']}; }}"
            f" QMessageBox QPushButton {{ background: {palette['accent']}; color: #0b1220; border-radius: 10px;"
            f" padding: 6px 12px; font-weight: 700; }}"
        )
        if self._password_dialog:
            self._password_dialog.setStyleSheet(dialog_style)

    def _build_ui(self):
        self.setWindowTitle("AutoWake")
        self.resize(720, 660)
        self.setMinimumSize(680, 620)
        icon = load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        central = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        top_bar = QtWidgets.QFrame(objectName="TopBar")
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 12, 12, 12)
        title_box = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("AutoWake")
        title.setObjectName("TopTitle")
        title_box.addWidget(title)
        top_layout.addLayout(title_box)
        logo_label = ClickableLabel()
        logo_label.setObjectName("TopLogo")
        logo_label.setContentsMargins(14, 0, 2, 0)
        logo_path = resource_path(APP_LOGO_PATH)
        if os.path.exists(logo_path):
            logo_pixmap = QtGui.QPixmap(logo_path)
            if not logo_pixmap.isNull():
                logo_label.setPixmap(logo_pixmap.scaledToHeight(34, QtCore.Qt.SmoothTransformation))
        logo_label.doubleClicked.connect(self._open_easter_egg)
        top_layout.addWidget(logo_label)
        top_layout.addStretch()
        self.start_button = QtWidgets.QPushButton("웨이크업 시작")
        self.stop_button = QtWidgets.QPushButton("웨이크업 중지")
        self.start_button.setObjectName("StartButton")
        self.stop_button.setObjectName("StopButton")
        self.start_button.clicked.connect(self._start_workers)
        self.stop_button.clicked.connect(self._stop_workers)
        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        self.state_label = QtWidgets.QLabel("● 상태: 중지됨")
        self.state_label.setObjectName("StatePill")
        self.state_label.setAlignment(QtCore.Qt.AlignRight)
        right_box = QtWidgets.QVBoxLayout()
        right_box.addLayout(button_row)
        right_box.addWidget(self.state_label)
        top_layout.addLayout(right_box)
        main_layout.addWidget(top_bar)

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setMovable(False)
        tabs.setUsesScrollButtons(True)
        tabs.setElideMode(QtCore.Qt.ElideRight)

        self.audio_card = FancyCard(
            "음원",
            "YouTube 포함 음원을 별도 프로세스로 실행하고 자동 재생합니다.",
        )
        self._build_audio_section(self.audio_card.body_layout)
        audio_tab = QtWidgets.QWidget()
        audio_layout = QtWidgets.QVBoxLayout(audio_tab)
        audio_layout.addWidget(self.audio_card)
        audio_layout.addStretch()

        self.target_card = FancyCard(
            "URL",
            "키오스크/전체화면/일반/최소화 모드를 선택할 수 있는 URL 창입니다.",
        )
        self._build_target_section(self.target_card.body_layout)
        target_tab = QtWidgets.QWidget()
        target_layout = QtWidgets.QVBoxLayout(target_tab)
        target_layout.addWidget(self.target_card)
        target_layout.addStretch()

        self.saver_card = FancyCard(
            "스크린세이버",
            "사용자 지정 이미지 또는 자동 생성 안내 문구로 세이버를 표시합니다.",
        )
        self._build_saver_section(self.saver_card.body_layout)
        saver_tab = QtWidgets.QWidget()
        saver_layout = QtWidgets.QVBoxLayout(saver_tab)
        saver_layout.addWidget(self.saver_card)
        saver_layout.addStretch()

        self.general_card = FancyCard(
            "프로그램 설정",
            "비밀번호, 테마, 설정 저장 위치를 관리합니다.",
        )
        self._build_settings_section(self.general_card.body_layout)
        settings_tab = QtWidgets.QWidget()
        settings_layout = QtWidgets.QVBoxLayout(settings_tab)
        settings_layout.addWidget(self.general_card)
        settings_layout.addStretch()

        self.credits_card = FancyCard(
            "크레딧",
            "프로그램 제작 정보를 확인합니다.",
        )
        self._build_credits_section(self.credits_card.body_layout)
        credits_tab = QtWidgets.QWidget()
        credits_layout = QtWidgets.QVBoxLayout(credits_tab)
        credits_layout.addWidget(self.credits_card)
        credits_layout.addStretch()

        tabs.addTab(audio_tab, "음원 옵션")
        tabs.addTab(target_tab, "URL 옵션")
        tabs.addTab(saver_tab, "스크린 세이버 옵션")
        tabs.addTab(settings_tab, "프로그램 설정")
        tabs.addTab(credits_tab, "크레딧")

        main_layout.addWidget(tabs)
        self.setCentralWidget(central)

    def _build_audio_section(self, layout: QtWidgets.QVBoxLayout):
        self.audio_enabled = StyledToggle("음원 사용")
        self._register_toggle(self.audio_enabled)
        layout.addWidget(self.audio_enabled)

        form = QtWidgets.QFormLayout()
        self.audio_url = QtWidgets.QLineEdit()
        self.audio_url.setReadOnly(True)
        self.audio_url_edit = QtWidgets.QPushButton("수정")
        self.audio_url_edit.clicked.connect(self._edit_audio_urls)
        audio_url_row = QtWidgets.QHBoxLayout()
        audio_url_row.addWidget(self.audio_url)
        audio_url_row.addWidget(self.audio_url_edit)
        self.audio_mode = ModeSelector(
            ["minimized", "normal", "fullscreen", "kiosk"],
            labels={"minimized": "최소화", "normal": "일반 창", "fullscreen": "전체화면", "kiosk": "키오스크"},
        )
        self.audio_start_delay = StepperInput()
        self.audio_start_delay.setRange(0.0, 60.0)
        self.audio_start_delay.setSingleStep(0.5)
        self.audio_start_delay.setDecimals(2)
        self.audio_relaunch_cooldown = StepperInput()
        self.audio_relaunch_cooldown.setRange(1.0, 6000.0)
        self.audio_relaunch_cooldown.setSingleStep(1.0)
        self.audio_relaunch_cooldown.setDecimals(2)
        self.audio_minimize_delay = StepperInput()
        self.audio_minimize_delay.setRange(1.0, 30.0)
        self.audio_minimize_delay.setSingleStep(0.5)
        self.audio_minimize_delay.setDecimals(2)
        self.audio_launch_group = QtWidgets.QButtonGroup(self)
        self.audio_launch_chrome = QtWidgets.QRadioButton("크롬으로 실행")
        self.audio_launch_pwa = QtWidgets.QRadioButton("YouTube 앱(PWA)으로 실행")
        self.audio_launch_group.addButton(self.audio_launch_chrome)
        self.audio_launch_group.addButton(self.audio_launch_pwa)
        self.audio_launch_chrome.toggled.connect(self._update_audio_mode_availability)
        self.audio_launch_pwa.toggled.connect(self._update_audio_mode_availability)
        self.audio_pwa_status = QtWidgets.QLabel("")
        self.audio_pwa_status.setWordWrap(True)
        self.audio_pwa_command = QtWidgets.QLineEdit()
        self.audio_pwa_command.setReadOnly(True)
        self.audio_pwa_refresh = QtWidgets.QPushButton("PWA 탐색")
        self.audio_pwa_refresh.clicked.connect(self._handle_pwa_refresh)
        launch_row = QtWidgets.QHBoxLayout()
        launch_row.addWidget(self.audio_launch_chrome)
        launch_row.addWidget(self.audio_launch_pwa)
        launch_row.addStretch()
        refresh_row = QtWidgets.QHBoxLayout()
        refresh_row.addWidget(self.audio_pwa_status, 1)
        refresh_row.addWidget(self.audio_pwa_refresh)
        self.audio_repeat_mode = ModeSelector(
            ["repeat", "once"],
            labels={"repeat": "반복 실행", "once": "초기 1회 실행"},
        )
        form.addRow(self._label("음원 URL"), audio_url_row)
        form.addRow(self._label("실행 방식"), launch_row)
        form.addRow("", refresh_row)
        form.addRow("PWA 실행 명령", self.audio_pwa_command)
        form.addRow(self._label("시작 창 모드"), self.audio_mode)
        form.addRow(self._label("시작 지연(초)"), self.audio_start_delay)
        form.addRow(self._label("자동 재생 대기(초)"), self.audio_minimize_delay)
        form.addRow(self._label("재실행 쿨다운(초)"), self.audio_relaunch_cooldown)
        form.addRow(self._label("실행 정책"), self.audio_repeat_mode)
        layout.addLayout(form)

    @staticmethod
    def _label(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("FormLabel")
        return label

    def _format_url_summary(self, urls: list[str], fallback: str) -> str:
        cleaned = [item for item in (urls or []) if item]
        if not cleaned:
            return fallback
        if len(cleaned) == 1:
            return cleaned[0]
        return f"{cleaned[0]} 외 {len(cleaned) - 1}개"

    def _update_audio_url_display(self):
        self.audio_url.setText(self._format_url_summary(self.audio_urls, DEFAULT_AUDIO_URL))

    def _update_audio_mode_availability(self):
        use_pwa = self.audio_launch_pwa.isChecked()
        if use_pwa:
            enabled = {"minimized", "normal"}
        else:
            enabled = set(self.audio_mode._buttons.keys())
        self.audio_mode.setEnabledOptions(enabled)
        if self.audio_mode.currentText() not in enabled:
            self.audio_mode.setCurrentText("normal" if "normal" in enabled else next(iter(enabled), ""))

    def _update_target_url_display(self):
        self.target_url.setText(self._format_url_summary(self.target_urls, DEFAULT_URL))

    def _edit_audio_urls(self):
        dialog = UrlListDialog("음원 URL 편집", list(self.audio_urls), self.palette, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            urls = dialog.urls()
            self.audio_urls = urls or [DEFAULT_AUDIO_URL]
            self._update_audio_url_display()
            self._autosave()

    def _edit_target_urls(self):
        dialog = UrlListDialog("URL 목록 편집", list(self.target_urls), self.palette, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            urls = dialog.urls()
            self.target_urls = urls or [DEFAULT_URL]
            self._update_target_url_display()
            self._autosave()

    def _register_toggle(self, toggle: StyledToggle) -> None:
        if not hasattr(self, "_toggles"):
            self._toggles = []
        self._toggles.append(toggle)
        toggle.set_palette(self.palette)

    def _build_target_section(self, layout: QtWidgets.QVBoxLayout):
        self.target_enabled = StyledToggle("URL 사용")
        self._register_toggle(self.target_enabled)
        layout.addWidget(self.target_enabled)

        form = QtWidgets.QFormLayout()
        self.target_url = QtWidgets.QLineEdit()
        self.target_url.setReadOnly(True)
        self.target_url_edit = QtWidgets.QPushButton("수정")
        self.target_url_edit.clicked.connect(self._edit_target_urls)
        target_url_row = QtWidgets.QHBoxLayout()
        target_url_row.addWidget(self.target_url)
        target_url_row.addWidget(self.target_url_edit)
        self.target_mode = ModeSelector(
            ["minimized", "normal", "fullscreen", "kiosk"],
            labels={
                "minimized": "최소화",
                "normal": "일반 창",
                "fullscreen": "전체 화면",
                "kiosk": "키오스크",
            },
        )
        self.target_start_delay = StepperInput()
        self.target_start_delay.setRange(0.0, 60.0)
        self.target_start_delay.setSingleStep(0.5)
        self.target_start_delay.setDecimals(2)
        self.target_relaunch_cooldown = StepperInput()
        self.target_relaunch_cooldown.setRange(1.0, 6000.0)
        self.target_relaunch_cooldown.setSingleStep(1.0)
        self.target_relaunch_cooldown.setDecimals(2)
        self.target_repeat_mode = ModeSelector(
            ["repeat", "once"],
            labels={"repeat": "반복 실행", "once": "초기 1회 실행"},
        )
        form.addRow(self._label("URL"), target_url_row)
        form.addRow(self._label("시작 창 모드"), self.target_mode)
        form.addRow(self._label("시작 지연(초)"), self.target_start_delay)
        form.addRow(self._label("재실행 쿨다운(초)"), self.target_relaunch_cooldown)
        form.addRow(self._label("실행 방식"), self.target_repeat_mode)
        layout.addLayout(form)

    def _build_saver_section(self, layout: QtWidgets.QVBoxLayout):
        self.saver_enabled = StyledToggle("스크린세이버 사용")
        self._register_toggle(self.saver_enabled)
        layout.addWidget(self.saver_enabled)

        form = QtWidgets.QFormLayout()
        self.saver_mode = ModeSelector(
            ["bundled", "path", "generated"],
            labels={"bundled": "기본 이미지", "path": "사용자 지정", "generated": "로드 실패 자동 생성"},
        )
        self.saver_image_path = QtWidgets.QLineEdit()
        self.saver_browse_button = QtWidgets.QPushButton("찾기")
        self.saver_browse_button.clicked.connect(self._browse_image)
        self.saver_mode.currentTextChanged.connect(self._update_saver_path_controls)
        self.saver_path_row = QtWidgets.QWidget()
        image_row = QtWidgets.QHBoxLayout(self.saver_path_row)
        image_row.setContentsMargins(0, 0, 0, 0)
        image_row.addWidget(self.saver_image_path)
        image_row.addWidget(self.saver_browse_button)

        self.saver_idle_delay = StepperInput()
        self.saver_idle_delay.setRange(1.0, 3600.0)
        self.saver_idle_delay.setSingleStep(1.0)
        self.saver_idle_delay.setDecimals(2)
        self.saver_active_threshold = StepperInput()
        self.saver_active_threshold.setRange(0.1, 60.0)
        self.saver_active_threshold.setSingleStep(0.1)
        self.saver_active_threshold.setDecimals(2)
        self.saver_poll = StepperInput()
        self.saver_poll.setRange(0.1, 10.0)
        self.saver_poll.setSingleStep(0.1)
        self.saver_poll.setDecimals(2)
        self.saver_start_delay = StepperInput()
        self.saver_start_delay.setRange(0.0, 60.0)
        self.saver_start_delay.setSingleStep(0.5)
        self.saver_start_delay.setDecimals(2)

        form.addRow(self._label("이미지 모드"), self.saver_mode)
        self.saver_display_mode = ModeSelector(
            ["full", "workarea"],
            labels={"full": "전체 화면", "workarea": "작업 표시줄 유지"},
        )
        form.addRow(self._label("이미지 표시"), self.saver_display_mode)
        self.saver_path_label = self._label("이미지 경로")
        form.addRow(self.saver_path_label, self.saver_path_row)
        form.addRow(self._label("표시 대기(초) (유휴 시간)"), self.saver_idle_delay)
        form.addRow(self._label("활동 감지 임계(초) (입력 감지)"), self.saver_active_threshold)
        form.addRow(self._label("폴링 주기(초) (상태 확인)"), self.saver_poll)
        form.addRow(self._label("시작 지연(초)"), self.saver_start_delay)
        layout.addLayout(form)
        self._update_saver_path_controls()

    def _update_saver_path_controls(self, mode: Optional[str] = None) -> None:
        selected_mode = mode or self.saver_mode.currentText()
        enabled = selected_mode == "path"
        self.saver_image_path.setEnabled(enabled)
        self.saver_browse_button.setEnabled(enabled)
        self.saver_path_row.setVisible(enabled)
        self.saver_path_label.setVisible(enabled)

    def _build_settings_section(self, layout: QtWidgets.QVBoxLayout):
        self.notice_enabled = StyledToggle("안내 팝업 표시")
        self._register_toggle(self.notice_enabled)
        layout.addWidget(self.notice_enabled)
        self.notice_edit_button = QtWidgets.QPushButton("안내 팝업 수정")
        self.notice_edit_button.clicked.connect(self._open_notice_editor)
        self.notice_edit_button.setFixedWidth(160)
        layout.addWidget(self.notice_edit_button)

        form = QtWidgets.QFormLayout()
        self.accent_color_button = QtWidgets.QPushButton("변경")
        self.accent_color_button.setObjectName("ThemeColorButton")
        self.accent_color_button.clicked.connect(self._open_accent_color_dialog)
        self.accent_color_button.setFixedWidth(140)
        form.addRow(self._label("테마 색상"), self.accent_color_button)
        layout.addLayout(form)

        path_row = QtWidgets.QHBoxLayout()
        self.config_path = QtWidgets.QLineEdit()
        self.config_path.setReadOnly(True)
        open_button = QtWidgets.QPushButton("설정 파일 경로 변경")
        open_button.clicked.connect(self._change_work_dir)
        open_button.setFixedWidth(160)
        path_row.addWidget(self.config_path)
        path_row.addWidget(open_button)
        layout.addLayout(path_row)

        self.change_password_button = QtWidgets.QPushButton("비밀번호 변경")
        self.change_password_button.clicked.connect(self._change_password)
        self.change_password_button.setFixedWidth(140)
        layout.addWidget(self.change_password_button)

    def _build_credits_section(self, layout: QtWidgets.QVBoxLayout) -> None:
        title = QtWidgets.QLabel(f"<b>{APP_NAME}</b> 제작 크레딧")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setProperty("popup-role", "body")
        layout.addWidget(title)
        grid = QtWidgets.QFormLayout()
        grid.setLabelAlignment(QtCore.Qt.AlignRight)
        grid.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        grid.setVerticalSpacing(8)
        grid.addRow("버전", QtWidgets.QLabel(APP_VERSION))
        grid.addRow("제작자", QtWidgets.QLabel(AUTHOR_NAME))
        grid.addRow("제작 날짜", QtWidgets.QLabel(BUILD_DATE))
        grid.addRow(
            "저작권",
            QtWidgets.QLabel("© 2026 Zolt46 - PSW - Emanon108. All rights reserved."),
        )
        grid.addRow("문의", QtWidgets.QLabel("다산정보관 참고자료실 데스크"))
        grid_widget = QtWidgets.QWidget()
        grid_widget.setLayout(grid)
        layout.addWidget(grid_widget)
        note = QtWidgets.QLabel("\n• 로고를 더블 클릭하면 숨겨진 이야기가 열립니다.")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _open_easter_egg(self) -> None:
        dialog = EasterEggDialog(self)
        dialog.exec()

    def _load_notice_config(self, cfg: AppConfig) -> None:
        self.notice_config = {
            "notice_title": cfg.notice_title,
            "notice_body": cfg.notice_body,
            "notice_footer": cfg.notice_footer,
            "notice_body_font_size": cfg.notice_body_font_size,
            "notice_body_bold": cfg.notice_body_bold,
            "notice_body_italic": cfg.notice_body_italic,
            "notice_body_align": cfg.notice_body_align,
            "notice_body_font_family": cfg.notice_body_font_family,
            "notice_footer_font_size": cfg.notice_footer_font_size,
            "notice_footer_bold": cfg.notice_footer_bold,
            "notice_footer_italic": cfg.notice_footer_italic,
            "notice_footer_align": cfg.notice_footer_align,
            "notice_footer_font_family": cfg.notice_footer_font_family,
            "notice_frame_color": cfg.notice_frame_color,
            "notice_frame_padding": cfg.notice_frame_padding,
            "notice_repeat_enabled": cfg.notice_repeat_enabled,
            "notice_repeat_interval_min": cfg.notice_repeat_interval_min,
            "notice_window_width": cfg.notice_window_width,
            "notice_window_height": cfg.notice_window_height,
            "notice_window_preset": cfg.notice_window_preset,
            "notice_image_mode": cfg.notice_image_mode,
            "notice_image_path": cfg.notice_image_path,
            "notice_bundled_image": cfg.notice_bundled_image,
            "notice_image_height": cfg.notice_image_height,
        }

    def _open_notice_editor(self) -> None:
        try:
            cfg = replace(self.cfg, **(self.notice_config or {}))
            dialog = NoticeConfigDialog(self.palette, cfg, self)
            self._bring_dialog_to_front(dialog)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            dialog.setFocus()
            if dialog.exec() != QtWidgets.QDialog.Accepted:
                return
            self.notice_config = dialog.get_notice_config()
            self._save_config()
        except Exception as exc:
            log(f"NOTICE dialog error: {exc}")
            QtWidgets.QMessageBox.warning(
                self,
                "안내 팝업 오류",
                "안내 팝업 구성 창을 여는 중 오류가 발생했습니다.\n"
                "로그를 확인해주세요.",
            )

    def _browse_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "이미지 파일 선택",
            "",
            "Image files (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if path:
            self.saver_image_path.setText(path)
            self._autosave()

    def _open_work_dir(self):
        try:
            os.startfile(self.cfg.work_dir)
        except Exception as exc:
            log(f"OPEN work dir error: {exc}")

    def _change_work_dir(self):
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "설정 파일 경로 선택",
            self.cfg.work_dir or WORK_DIR,
        )
        if not new_dir:
            return
        try:
            os.makedirs(new_dir, exist_ok=True)
            old_path = config_file_path(self.cfg.work_dir)
            new_path = config_file_path(new_dir)
            if os.path.exists(old_path) and old_path != new_path:
                try:
                    shutil.copy2(old_path, new_path)
                except Exception as exc:
                    log(f"CONFIG copy error: {exc}")
            self.cfg.work_dir = new_dir
            save_config(self.cfg)
            self.config_path.setText(new_dir)
            if self.is_running:
                self.process_manager.stop_all()
                self._sync_workers()
        except Exception as exc:
            log(f"CHANGE work dir error: {exc}")

    def _ensure_default_password(self):
        if not self.cfg.password_hash:
            self.cfg.password_hash, self.cfg.password_salt = create_password_hash("0000")
            self.cfg.admin_password = ""

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        if not self._ui_active:
            update_notice_state_counter(self.cfg.work_dir, "ui_active", 1)
            self._ui_active = True
        super().showEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        if self._ui_active:
            update_notice_state_counter(self.cfg.work_dir, "ui_active", -1)
            self._ui_active = False
        super().hideEvent(event)

    def _change_password(self):
        dialog = PasswordChangeDialog(self.palette, self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        current = dialog.current_password.text()
        new_password = dialog.new_password.text()
        confirm = dialog.confirm_password.text()
        if not current:
            QtWidgets.QMessageBox.warning(self, "비밀번호 오류", "현재 비밀번호를 입력하세요.")
            return
        if not verify_password(current, self.cfg.password_hash, self.cfg.password_salt):
            QtWidgets.QMessageBox.warning(self, "비밀번호 오류", "현재 비밀번호가 올바르지 않습니다.")
            return
        if not new_password:
            QtWidgets.QMessageBox.warning(self, "비밀번호 오류", "새 비밀번호를 입력하세요.")
            return
        if not confirm:
            QtWidgets.QMessageBox.warning(self, "비밀번호 오류", "비밀번호 확인을 입력하세요.")
            return
        if new_password != confirm:
            QtWidgets.QMessageBox.warning(self, "비밀번호 오류", "비밀번호 확인이 일치하지 않습니다.")
            return
        self.cfg.password_hash, self.cfg.password_salt = create_password_hash(new_password)
        self.cfg.admin_password = ""
        save_config(self.cfg)

    def _update_accent_color_button(self, color_hex: str) -> None:
        if not color_hex:
            color_hex = self.palette["accent"]
        self.accent_color_button.setStyleSheet(
            " ".join(
                [
                    f"background: {color_hex};",
                    "color: #0b1220;",
                    "border-radius: 10px;",
                    "padding: 6px 12px;",
                    "font-weight: 700;",
                ]
            )
        )

    def _open_accent_color_dialog(self):
        current_color = QtGui.QColor(self.cfg.accent_color or self.palette["accent"])
        dialog = QtWidgets.QColorDialog(current_color, self)
        dialog.setOption(QtWidgets.QColorDialog.ShowAlphaChannel, False)
        dialog.setOption(QtWidgets.QColorDialog.DontUseNativeDialog, True)
        dialog.currentColorChanged.connect(
            lambda color: self._update_accent_color_button(color.name())
        )
        original_color = self.cfg.accent_color
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            selected = dialog.currentColor().name()
            self.cfg.accent_color = selected
            save_config(self.cfg)
            self._apply_palette()
        else:
            self._update_accent_color_button(original_color or self.palette["accent"])

    def _build_tray_icon(self) -> QtGui.QIcon:
        icon = load_app_icon()
        if not icon.isNull():
            return icon
        size = 64
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setBrush(QtGui.QColor(self.palette["accent"]))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(6, 6, size - 12, size - 12)
        painter.setPen(QtGui.QPen(QtGui.QColor(self.palette["bg"]), 6))
        painter.drawLine(size // 2, 14, size // 2, size - 14)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _setup_tray(self):
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_menu = QtWidgets.QMenu()
        self.action_start = self.tray_menu.addAction("시작")
        self.action_stop = self.tray_menu.addAction("중지")
        self.action_settings = self.tray_menu.addAction("설정")
        self.tray_menu.addSeparator()
        self.action_quit = self.tray_menu.addAction("종료")

        self.action_start.triggered.connect(self._start_workers)
        self.action_stop.triggered.connect(self._stop_workers)
        self.action_settings.triggered.connect(self._request_settings_open)
        self.action_quit.triggered.connect(self._quit_app)

        self.tray_icon = QtWidgets.QSystemTrayIcon(self._build_tray_icon(), self)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()
        self._update_tray_actions()

    def _tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason):
        if reason == QtWidgets.QSystemTrayIcon.Context and self.tray_menu:
            self.tray_menu.popup(QtGui.QCursor.pos())
        elif reason == QtWidgets.QSystemTrayIcon.Trigger:
            self._request_settings_open()

    def _update_tray_actions(self):
        if not self.action_start or not self.action_stop:
            return
        self.action_start.setEnabled(not self.is_running)
        self.action_stop.setEnabled(self.is_running)

    def _bring_window_to_front(self) -> None:
        if self._raising_window:
            return
        self._raising_window = True
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        QtCore.QTimer.singleShot(0, self._clear_window_on_top)

    def _clear_window_on_top(self) -> None:
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
        self.show()
        self._raising_window = False

    def _bring_dialog_to_front(self, dialog: QtWidgets.QDialog) -> None:
        dialog.setWindowFlags(dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        dialog.setWindowState(
            dialog.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.setFocus()

    def _request_settings_open(self):
        if self._opening_settings and not (
            self._password_dialog and self._password_dialog.isVisible()
        ):
            self._opening_settings = False
        if self._opening_settings:
            return
        if self._password_dialog:
            self._password_dialog.close()
            self._password_dialog = None
        if self.isVisible() or self.isMinimized():
            self._bring_window_to_front()
            return
        self._opening_settings = True
        self._password_dialog = PasswordDialog(
            self._verify_password,
            self.palette,
            self.cfg.work_dir,
            self,
        )
        self._password_dialog.finished.connect(self._handle_password_finished)
        self._password_dialog.open()
        self._bring_dialog_to_front(self._password_dialog)

    def _verify_password(self, value: str) -> bool:
        return verify_password(value, self.cfg.password_hash, self.cfg.password_salt)

    def _handle_password_finished(self, result: int) -> None:
        if result == QtWidgets.QDialog.Accepted:
            self.showNormal()
            self.resize(self.minimumSize())
            self._bring_window_to_front()
        self._password_dialog = None
        self._opening_settings = False

    def _quit_app(self):
        self.process_manager.stop_all()
        if self.tray_icon:
            self.tray_icon.hide()
        QtWidgets.QApplication.quit()

    def closeEvent(self, event: QtGui.QCloseEvent):
        event.ignore()
        self.hide()

    def _load_config_to_ui(self):
        self._loading = True
        cfg = self.cfg
        self.audio_enabled.setChecked(cfg.audio_enabled)
        self.audio_urls = list(cfg.audio_urls or [cfg.audio_url])
        self._update_audio_url_display()
        self.audio_mode.setCurrentText(cfg.audio_window_mode)
        self.audio_start_delay.setValue(cfg.audio_start_delay_sec)
        self.audio_minimize_delay.setValue(cfg.audio_minimize_delay_sec)
        self.audio_relaunch_cooldown.setValue(cfg.audio_relaunch_cooldown_sec)
        self.audio_repeat_mode.setCurrentText(cfg.audio_repeat_mode)
        if cfg.audio_launch_mode == "pwa" and cfg.audio_pwa_app_id:
            self.audio_pwa_app_id_value = cfg.audio_pwa_app_id
            self.audio_pwa_browser_hint = cfg.audio_pwa_browser_hint
            self.audio_pwa_arguments = cfg.audio_pwa_arguments
            self.audio_pwa_command.setText(cfg.audio_pwa_command_preview)
            self.audio_pwa_status.setText(f"PWA 설정됨: {cfg.audio_pwa_app_id}")
            self.audio_launch_pwa.setEnabled(True)
            self.audio_launch_pwa.setChecked(True)
        else:
            self.audio_launch_chrome.setChecked(True)
            self._refresh_pwa_info()
        self._update_audio_mode_availability()

        self.target_enabled.setChecked(cfg.target_enabled)
        self.target_urls = list(cfg.urls or [cfg.url])
        self._update_target_url_display()
        self.target_mode.setCurrentText(cfg.target_window_mode)
        self.target_start_delay.setValue(cfg.target_start_delay_sec)
        self.target_relaunch_cooldown.setValue(cfg.target_relaunch_cooldown_sec)
        self.target_repeat_mode.setCurrentText(cfg.target_repeat_mode)

        self.saver_enabled.setChecked(cfg.saver_enabled)
        self.saver_mode.setCurrentText(cfg.saver_image_mode)
        self.saver_display_mode.setCurrentText(cfg.saver_display_mode)
        self.saver_image_path.setText(cfg.image_path)
        self._update_saver_path_controls(cfg.saver_image_mode)
        self.saver_idle_delay.setValue(cfg.idle_to_show_sec)
        self.saver_active_threshold.setValue(cfg.active_threshold_sec)
        self.saver_poll.setValue(cfg.poll_sec)
        self.saver_start_delay.setValue(cfg.saver_start_delay_sec)

        self.notice_enabled.setChecked(cfg.notice_enabled)
        self._load_notice_config(cfg)
        self._update_accent_color_button(cfg.accent_color or self.palette["accent"])
        self.config_path.setText(cfg.work_dir)
        self._update_run_state_labels()
        self._loading = False

    def _gather_config(self) -> AppConfig:
        target_mode = self.target_mode.currentText()
        target_urls = list(self.target_urls or [])
        audio_urls = list(self.audio_urls or [])
        primary_target = target_urls[0] if target_urls else DEFAULT_URL
        primary_audio = audio_urls[0] if audio_urls else DEFAULT_AUDIO_URL
        notice_config = self.notice_config or {}
        cfg = AppConfig(
            url=primary_target,
            urls=target_urls or [primary_target],
            image_path=self.saver_image_path.text(),
            work_dir=self.cfg.work_dir,
            idle_to_show_sec=self.saver_idle_delay.value(),
            active_threshold_sec=self.saver_active_threshold.value(),
            poll_sec=self.saver_poll.value(),
            chrome_relaunch_cooldown_sec=self.cfg.chrome_relaunch_cooldown_sec,
            chrome_fullscreen=target_mode in {"fullscreen", "kiosk"},
            chrome_kiosk=target_mode == "kiosk",
            saver_enabled=self.saver_enabled.isChecked(),
            chrome_repeat=self.cfg.chrome_repeat,
            ui_theme="accent",
            saver_image_mode=self.saver_mode.currentText(),
            saver_display_mode=self.saver_display_mode.currentText(),
            audio_url=primary_audio,
            audio_urls=audio_urls or [primary_audio],
            audio_enabled=self.audio_enabled.isChecked(),
            audio_window_mode=self.audio_mode.currentText(),
            audio_start_delay_sec=self.audio_start_delay.value(),
            audio_minimize_delay_sec=self.audio_minimize_delay.value(),
            audio_relaunch_cooldown_sec=self.audio_relaunch_cooldown.value(),
            audio_repeat_mode=self.audio_repeat_mode.currentText(),
            audio_launch_mode="pwa" if self.audio_launch_pwa.isChecked() else "chrome",
            audio_pwa_app_id=self.audio_pwa_app_id_value,
            audio_pwa_command_preview=self.audio_pwa_command.text().strip(),
            audio_pwa_browser_hint=getattr(self, "audio_pwa_browser_hint", ""),
            audio_pwa_arguments=getattr(self, "audio_pwa_arguments", ""),
            audio_pwa_use_proxy=bool(getattr(self, "audio_pwa_use_proxy", False)),
            target_enabled=self.target_enabled.isChecked(),
            target_window_mode=target_mode,
            target_start_delay_sec=self.target_start_delay.value(),
            target_relaunch_cooldown_sec=self.target_relaunch_cooldown.value(),
            target_refocus_interval_sec=self.cfg.target_refocus_interval_sec,
            target_repeat_mode=self.target_repeat_mode.currentText(),
            saver_start_delay_sec=self.saver_start_delay.value(),
            notice_enabled=self.notice_enabled.isChecked(),
            notice_title=str(notice_config.get("notice_title", self.cfg.notice_title)),
            notice_body=str(notice_config.get("notice_body", self.cfg.notice_body)),
            notice_footer=str(notice_config.get("notice_footer", self.cfg.notice_footer)),
            notice_body_font_size=int(
                notice_config.get("notice_body_font_size", self.cfg.notice_body_font_size)
            ),
            notice_body_bold=bool(
                notice_config.get("notice_body_bold", self.cfg.notice_body_bold)
            ),
            notice_body_italic=bool(
                notice_config.get("notice_body_italic", self.cfg.notice_body_italic)
            ),
            notice_body_align=str(
                notice_config.get("notice_body_align", self.cfg.notice_body_align)
            ),
            notice_body_font_family=str(
                notice_config.get("notice_body_font_family", self.cfg.notice_body_font_family)
            ),
            notice_footer_font_size=int(
                notice_config.get("notice_footer_font_size", self.cfg.notice_footer_font_size)
            ),
            notice_footer_bold=bool(
                notice_config.get("notice_footer_bold", self.cfg.notice_footer_bold)
            ),
            notice_footer_italic=bool(
                notice_config.get("notice_footer_italic", self.cfg.notice_footer_italic)
            ),
            notice_footer_align=str(
                notice_config.get("notice_footer_align", self.cfg.notice_footer_align)
            ),
            notice_footer_font_family=str(
                notice_config.get("notice_footer_font_family", self.cfg.notice_footer_font_family)
            ),
            notice_frame_color=str(
                notice_config.get("notice_frame_color", self.cfg.notice_frame_color)
            ),
            notice_frame_padding=int(
                notice_config.get("notice_frame_padding", self.cfg.notice_frame_padding)
            ),
            notice_repeat_enabled=bool(
                notice_config.get("notice_repeat_enabled", self.cfg.notice_repeat_enabled)
            ),
            notice_repeat_interval_min=int(
                notice_config.get(
                    "notice_repeat_interval_min", self.cfg.notice_repeat_interval_min
                )
            ),
            notice_window_width=int(
                notice_config.get("notice_window_width", self.cfg.notice_window_width)
            ),
            notice_window_height=int(
                notice_config.get("notice_window_height", self.cfg.notice_window_height)
            ),
            notice_window_preset=str(
                notice_config.get("notice_window_preset", self.cfg.notice_window_preset)
            ),
            notice_image_mode=str(
                notice_config.get("notice_image_mode", self.cfg.notice_image_mode)
            ),
            notice_image_path=str(
                notice_config.get("notice_image_path", self.cfg.notice_image_path)
            ),
            notice_bundled_image=str(
                notice_config.get("notice_bundled_image", self.cfg.notice_bundled_image)
            ),
            notice_image_height=int(
                notice_config.get("notice_image_height", self.cfg.notice_image_height)
            ),
            admin_password="",
            password_hash=self.cfg.password_hash,
            password_salt=self.cfg.password_salt,
            accent_theme=self.cfg.accent_theme,
            accent_color=self.cfg.accent_color,
        )
        return cfg

    def _save_config(self):
        self.cfg = self._gather_config()
        save_config(self.cfg)
        self._apply_palette()

    def _connect_autosave(self):
        widgets = [
            self.audio_enabled,
            self.target_enabled,
            self.saver_enabled,
            self.notice_enabled,
        ]
        for widget in widgets:
            widget.toggled.connect(self._autosave)
        for widget in [
            self.saver_image_path,
        ]:
            widget.textEdited.connect(self._autosave)
        for widget in [
            self.audio_mode,
            self.target_mode,
            self.saver_mode,
            self.saver_display_mode,
            self.audio_repeat_mode,
            self.target_repeat_mode,
        ]:
            widget.currentTextChanged.connect(self._autosave)
        self.audio_launch_chrome.toggled.connect(self._autosave)
        for widget in [
            self.audio_start_delay,
            self.audio_minimize_delay,
            self.audio_relaunch_cooldown,
            self.target_start_delay,
            self.target_relaunch_cooldown,
            self.saver_idle_delay,
            self.saver_active_threshold,
            self.saver_poll,
            self.saver_start_delay,
        ]:
            widget.valueChanged.connect(self._autosave)

    def _autosave(self, *_args):
        if getattr(self, "_loading", False):
            return
        self._save_config()
        self._sync_workers()

    def _refresh_pwa_preview(self) -> None:
        preview_url = ""
        if (self.audio_repeat_mode.currentText() or "").lower() == "once":
            audio_urls = list(self.audio_urls or [self.cfg.audio_url])
            preview_url = ensure_youtube_autoplay(audio_urls[0]) if audio_urls else ""
        self._refresh_pwa_info(preview_url)

    def _handle_pwa_refresh(self) -> None:
        preview_url = ""
        if (self.audio_repeat_mode.currentText() or "").lower() == "once":
            audio_urls = list(self.audio_urls or [self.cfg.audio_url])
            preview_url = ensure_youtube_autoplay(audio_urls[0]) if audio_urls else ""
        self._refresh_pwa_info(preview_url)

    def _refresh_pwa_info(self, preview_url: str = "") -> None:
        app_id, browser_hint, launcher_args, using_proxy = detect_youtube_pwa_app_id()
        self.audio_pwa_app_id_value = app_id
        self.audio_pwa_browser_hint = browser_hint
        self.audio_pwa_arguments = launcher_args
        self.audio_pwa_use_proxy = using_proxy
        if app_id:
            command_preview = build_pwa_command_preview(
                app_id,
                browser_hint,
                launcher_args,
                preview_url,
                self.audio_repeat_mode.currentText() == "repeat",
            )
            self.audio_pwa_command.setText(command_preview)
            self.audio_pwa_status.setText(f"PWA 탐색됨: {app_id}")
            self.audio_launch_pwa.setEnabled(True)
            if not self.audio_launch_chrome.isChecked() and not self.audio_launch_pwa.isChecked():
                self.audio_launch_pwa.setChecked(True)
        else:
            self.audio_pwa_command.setText("")
            self.audio_pwa_status.setText("PWA 탐색 실패: 크롬 실행으로 대체됩니다.")
            self.audio_launch_pwa.setEnabled(False)
            self.audio_launch_chrome.setChecked(True)
        self._update_audio_mode_availability()

    def _start_workers(self):
        self._save_config()
        if self.is_running:
            return
        self.is_running = True
        self._sync_workers()
        self._update_run_state_labels()

    def _stop_workers(self):
        self.process_manager.stop_all()
        self.is_running = False
        self._update_run_state_labels()

    def _sync_workers(self) -> None:
        if not self.is_running:
            return
        cfg = self.cfg
        if cfg.audio_enabled:
            self.process_manager.start("audio")
        else:
            self.process_manager.stop("audio")
        if cfg.target_enabled or cfg.notice_enabled:
            self.process_manager.start("target")
        else:
            self.process_manager.stop("target")
        if cfg.saver_enabled:
            self.process_manager.start("saver")
        else:
            self.process_manager.stop("saver")

    def _update_run_state_labels(self):
        if self.is_running:
            self.state_label.setText("● 상태: 실행 중")
            self.state_label.setStyleSheet(f"color: {self.palette['accent']};")
        else:
            self.state_label.setText("● 상태: 중지됨")
            self.state_label.setStyleSheet(f"color: {self.palette['text_muted']};")
        self.start_button.setEnabled(not self.is_running)
        self.stop_button.setEnabled(self.is_running)
        self._update_tray_actions()


class AudioWorker:
    def __init__(self):
        self.cfg = load_config()
        self.proc: Optional[subprocess.Popen] = None
        self.external_pid: Optional[int] = None
        self.last_minimized_pid: Optional[int] = None
        self.pending_minimize_pid: Optional[int] = None
        self.pending_minimize_at: Optional[float] = None
        self.pending_restore_pid: Optional[int] = None
        self.pending_restore_at: Optional[float] = None
        self.pending_restore_again_at: Optional[float] = None
        self.last_launch = 0.0
        self.pending_launch_at: Optional[float] = None
        self.last_config_signature: Optional[tuple] = None
        self.once_launched = False
        self.pwa_browser_hint = ""

    def run(self):
        while True:
            self.cfg = load_config()
            config_signature = (
                tuple(self.cfg.audio_urls or [self.cfg.audio_url]),
                self.cfg.audio_window_mode,
                self.cfg.audio_start_delay_sec,
                self.cfg.audio_relaunch_cooldown_sec,
                self.cfg.audio_enabled,
                self.cfg.audio_repeat_mode,
            )
            if self.last_config_signature is None:
                self.last_config_signature = config_signature
            elif config_signature != self.last_config_signature:
                self.last_config_signature = config_signature
                if self.proc and self.proc.poll() is None:
                    self._stop_proc()
                    self.pending_launch_at = time.time() + self.cfg.audio_start_delay_sec
                    self.last_launch = 0.0
                    self.once_launched = False
            if not self.cfg.audio_enabled:
                self._stop_proc()
                self.pending_launch_at = None
                self.external_pid = None
                self.once_launched = False
                time.sleep(self.cfg.poll_sec)
                continue
            if self.proc is None or self.proc.poll() is not None:
                launch_mode = (self.cfg.audio_launch_mode or "chrome").lower()
                if launch_mode == "pwa" and self.cfg.audio_pwa_app_id:
                    existing = find_chrome_processes_by_app_id(self.cfg.audio_pwa_app_id)
                    visible = [pid for pid in existing if find_window_handles_by_pid(pid)]
                    if visible:
                        self.external_pid = visible[0]
                        self.last_launch = time.time()
                        self.pending_launch_at = None
                        self.once_launched = True
                        time.sleep(self.cfg.poll_sec)
                        continue
                    if existing and time.time() - self.last_launch < self.cfg.audio_relaunch_cooldown_sec:
                        self.external_pid = existing[0]
                        self.last_launch = time.time()
                        self.pending_launch_at = None
                        self.once_launched = True
                        time.sleep(self.cfg.poll_sec)
                        continue
                else:
                    profile = os.path.join(self.cfg.work_dir, "chrome_profiles", "audio")
                    os.makedirs(profile, exist_ok=True)
                    existing = find_chrome_processes_by_profile(profile)
                    if len(existing) > 1:
                        visible = [pid for pid in existing if find_window_handles_by_pid(pid)]
                        keep_pid = visible[0] if visible else existing[0]
                        for pid in existing:
                            if pid != keep_pid:
                                terminate_process(pid)
                        existing = [keep_pid]
                    if existing:
                        self.external_pid = existing[0]
                        self.last_launch = time.time()
                        self.pending_launch_at = None
                        self.once_launched = True
                        time.sleep(self.cfg.poll_sec)
                        continue
                if self.cfg.audio_repeat_mode == "once" and self.once_launched:
                    time.sleep(self.cfg.poll_sec)
                    continue
                now = time.time()
                if now - self.last_launch >= self.cfg.audio_relaunch_cooldown_sec:
                    if self.pending_launch_at is None:
                        self.pending_launch_at = now + self.cfg.audio_start_delay_sec
            if self.pending_launch_at is not None:
                now = time.time()
                if now >= self.pending_launch_at:
                    launch_mode = (self.cfg.audio_launch_mode or "chrome").lower()
                    pwa_attempted = False
                    if launch_mode == "pwa" and self.cfg.audio_pwa_app_id:
                        pwa_attempted = True
                        browser_hint = self.cfg.audio_pwa_browser_hint or self.pwa_browser_hint
                        candidates = self.cfg.audio_urls or [self.cfg.audio_url]
                        url = ensure_youtube_autoplay(random.choice(candidates))
                        self.proc = launch_pwa(
                            self.cfg.audio_pwa_app_id,
                            browser_hint,
                            self.cfg.audio_pwa_arguments,
                            url,
                        )
                        if self.proc is None:
                            log("PWA launch failed; falling back to Chrome.")
                    if launch_mode != "chrome" and self.proc is not None:
                        pass
                    else:
                        if launch_mode != "chrome" and not pwa_attempted:
                            log("PWA app-id missing; falling back to Chrome.")
                        candidates = self.cfg.audio_urls or [self.cfg.audio_url]
                        url = ensure_youtube_autoplay(random.choice(candidates))
                        profile = os.path.join(self.cfg.work_dir, "chrome_profiles", "audio")
                        os.makedirs(profile, exist_ok=True)
                        chrome_mode = self.cfg.audio_window_mode
                        if (chrome_mode or "").lower() == "minimized":
                            chrome_mode = "normal"
                        self.proc = launch_chrome([url], profile, chrome_mode, True, True)
                    self.last_launch = time.time()
                    self.pending_launch_at = None
                    self.once_launched = True
                if (self.cfg.audio_window_mode or "").lower() == "minimized":
                    minimize_delay = max(1.0, float(self.cfg.audio_minimize_delay_sec))
                    if self.proc:
                        self.pending_minimize_pid = self.proc.pid
                        self.pending_restore_pid = self.proc.pid
                        self.pending_restore_at = time.time() + 0.3
                        self.pending_restore_again_at = time.time() + 1.2
                        self.pending_minimize_at = time.time() + minimize_delay
                    elif self.external_pid:
                        self.pending_minimize_pid = self.external_pid
                        self.pending_minimize_at = time.time() + minimize_delay
            if self.pending_restore_pid and (self.cfg.audio_window_mode or "").lower() == "minimized":
                if time.time() >= (self.pending_restore_at or 0):
                    if find_window_handles_by_pid(self.pending_restore_pid):
                        restore_window(self.pending_restore_pid)
                        self.pending_restore_pid = None
                        self.pending_restore_at = None
            if (
                self.pending_restore_again_at
                and (self.cfg.audio_window_mode or "").lower() == "minimized"
            ):
                if time.time() >= self.pending_restore_again_at:
                    pid = self.proc.pid if self.proc and self.proc.poll() is None else self.external_pid
                    if pid and find_window_handles_by_pid(pid):
                        restore_window(pid)
                    self.pending_restore_again_at = None
            if self.pending_minimize_pid and (self.cfg.audio_window_mode or "").lower() == "minimized":
                if time.time() >= (self.pending_minimize_at or 0):
                    if not find_window_handles_by_pid(self.pending_minimize_pid):
                        if (
                            (self.cfg.audio_launch_mode or "chrome").lower() == "pwa"
                            and self.cfg.audio_pwa_app_id
                        ):
                            candidates = [
                                pid
                                for pid in find_chrome_processes_by_app_id(self.cfg.audio_pwa_app_id)
                                if find_window_handles_by_pid(pid)
                            ]
                            if candidates:
                                self.pending_minimize_pid = candidates[0]
                    if find_window_handles_by_pid(self.pending_minimize_pid):
                        minimize_window(self.pending_minimize_pid)
                        self.last_minimized_pid = self.pending_minimize_pid
                        self.pending_minimize_pid = None
                        self.pending_minimize_at = None
            time.sleep(max(self.cfg.poll_sec, 0.2))

    def _stop_proc(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None
        if self.external_pid:
            terminate_process(self.external_pid)
        self.external_pid = None
        self.last_minimized_pid = None
        self.pending_minimize_pid = None
        self.pending_minimize_at = None
        self.pending_restore_pid = None
        self.pending_restore_at = None
        self.pending_restore_again_at = None
        self.pending_launch_at = None
        self.pending_launch_at = None


class TargetWorker(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.proc: Optional[subprocess.Popen] = None
        self.external_pid: Optional[int] = None
        self.last_minimized_pid: Optional[int] = None
        self.pending_minimize_pid: Optional[int] = None
        self.pending_minimize_at: Optional[float] = None
        self.last_launch = 0.0
        self.pending_launch_at: Optional[float] = None
        self.last_config_signature: Optional[tuple] = None
        self.palette_key = (self.cfg.accent_theme, self.cfg.accent_color)
        self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
        self.notice = NoticeWindow(self.palette, self.cfg)
        self.notice.closed.connect(self._dismiss_notice)
        self.notice_dismissed = False
        self.last_notice_enabled = self.cfg.notice_enabled
        state = read_notice_state(self.cfg.work_dir)
        self.last_saver_trigger_at = float(state.get("saver_trigger_at", 0.0))
        self.pending_notice_after_saver = False
        self.last_interaction_lock: Optional[bool] = None
        self.last_saver_active = False
        self.saver_release_hold_until = 0.0
        self.last_ui_active = False
        self.ui_release_hold_until = 0.0
        self.once_launched = False
        self.missing_window_since: Optional[float] = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(max(self.cfg.poll_sec, 0.2) * 1000))

    def _dismiss_notice(self):
        self.notice_dismissed = True
        write_notice_state(self.cfg.work_dir, notice_dismissed_at=time.time())

    def _tick(self):
        self.cfg = load_config()
        config_signature = (
            tuple(self.cfg.urls or [self.cfg.url]),
            self.cfg.target_window_mode,
            self.cfg.target_start_delay_sec,
            self.cfg.target_relaunch_cooldown_sec,
            self.cfg.target_enabled,
            self.cfg.target_repeat_mode,
        )
        if self.last_config_signature is None:
            self.last_config_signature = config_signature
        elif config_signature != self.last_config_signature:
            self.last_config_signature = config_signature
            if self.proc and self.proc.poll() is None:
                self._stop_proc()
                self.pending_launch_at = time.time() + self.cfg.target_start_delay_sec
                self.last_launch = 0.0
                self.once_launched = False
        new_key = (self.cfg.accent_theme, self.cfg.accent_color)
        if new_key != self.palette_key:
            self.palette_key = new_key
            self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
            self.notice.palette = self.palette
            self.notice._apply_palette()
        self.notice.update_content(self.cfg)
        if self.cfg.notice_enabled and not self.last_notice_enabled:
            self.notice_dismissed = False
        self.last_notice_enabled = self.cfg.notice_enabled

        state = read_notice_state(self.cfg.work_dir)
        ui_active = int(state.get("ui_active", 0)) > 0
        saver_active = float(state.get("saver_active", 0.0)) > 0.5
        if ui_active != self.last_ui_active:
            self.last_ui_active = ui_active
            if not ui_active:
                self.ui_release_hold_until = time.time() + 0.5
        if saver_active != self.last_saver_active:
            self.last_saver_active = saver_active
            if not saver_active:
                self.saver_release_hold_until = time.time() + 0.8
        saver_trigger_at = float(state.get("saver_trigger_at", 0.0))
        if saver_trigger_at > self.last_saver_trigger_at:
            self.last_saver_trigger_at = saver_trigger_at
            self.pending_notice_after_saver = True
            self.notice_dismissed = False

        dismissed_at = float(state.get("notice_dismissed_at", 0.0))
        if (
            not saver_active
            and not self.cfg.saver_enabled
            and self.cfg.notice_repeat_enabled
            and self.notice_dismissed
            and dismissed_at > 0
        ):
            interval_sec = max(1, int(self.cfg.notice_repeat_interval_min)) * 60
            if time.time() - dismissed_at >= interval_sec:
                self.notice_dismissed = False

        hold_notice = (
            time.time() < self.saver_release_hold_until
            or time.time() < self.ui_release_hold_until
        )
        if ui_active:
            if self.notice.isVisible():
                self.notice.set_interaction_lock(False)
                self.notice.lower()
            self.last_interaction_lock = False
        elif saver_active:
            if self.notice.isVisible():
                self.notice.hide()
            self.last_interaction_lock = None
        elif self.cfg.notice_enabled and not self.notice_dismissed and not hold_notice:
            if not self.notice.isVisible():
                self.notice.show_centered()
                now = time.time()
                write_notice_state(
                    self.cfg.work_dir,
                    notice_last_shown_at=now,
                    notice_dismissed_at=0.0,
                )
            if self.notice.isVisible():
                self.notice.raise_()
                self.notice.activateWindow()
            desired_lock = not ui_active
            if self.last_interaction_lock is None or desired_lock != self.last_interaction_lock:
                self.notice.set_interaction_lock(desired_lock)
                self.last_interaction_lock = desired_lock
            if self.pending_notice_after_saver:
                self.pending_notice_after_saver = False
        else:
            if self.notice.isVisible():
                self.notice.hide()
            self.last_interaction_lock = None

        if not self.cfg.target_enabled:
            self._stop_proc()
            self.pending_launch_at = None
            self.once_launched = False
            self.external_pid = None
            return

        if self._current_pid():
            if self._proc_has_visible_window():
                self.missing_window_since = None
            else:
                now = time.time()
                if self.missing_window_since is None:
                    self.missing_window_since = now
                elif now - self.missing_window_since >= 2.0:
                    self._stop_proc()
                    self.missing_window_since = None

        if self.proc is None or self.proc.poll() is not None:
            profile = os.path.join(self.cfg.work_dir, "chrome_profiles", "target")
            os.makedirs(profile, exist_ok=True)
            existing = [
                pid for pid in find_chrome_processes_by_profile(profile)
                if find_window_handles_by_pid(pid)
            ]
            if existing:
                self.external_pid = existing[0]
                self.last_launch = time.time()
                self.pending_launch_at = None
                self.once_launched = True
                return
            if self.cfg.target_repeat_mode == "once" and self.once_launched:
                return
            now = time.time()
            if now - self.last_launch >= self.cfg.target_relaunch_cooldown_sec:
                if self.pending_launch_at is None:
                    self.pending_launch_at = now + self.cfg.target_start_delay_sec

        if self.pending_launch_at is not None:
            now = time.time()
            if now >= self.pending_launch_at:
                profile = os.path.join(self.cfg.work_dir, "chrome_profiles", "target")
                os.makedirs(profile, exist_ok=True)
                urls = self.cfg.urls or [self.cfg.url]
                self.proc = launch_chrome(
                    urls,
                    profile,
                    self.cfg.target_window_mode,
                    False,
                    True,
                )
                self.last_launch = time.time()
                self.pending_launch_at = None
                self.once_launched = True
                self.missing_window_since = None
                if self.proc and (self.cfg.target_window_mode or "").lower() == "minimized":
                    self.pending_minimize_pid = self.proc.pid
                    self.pending_minimize_at = time.time() + 0.5

        if self.pending_minimize_pid and (self.cfg.target_window_mode or "").lower() == "minimized":
            if time.time() >= (self.pending_minimize_at or 0):
                if find_window_handles_by_pid(self.pending_minimize_pid):
                    minimize_window(self.pending_minimize_pid)
                    self.last_minimized_pid = self.pending_minimize_pid
                    self.pending_minimize_pid = None
                    self.pending_minimize_at = None

    def _stop_proc(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None
        self.external_pid = None
        self.last_minimized_pid = None
        self.pending_minimize_pid = None
        self.pending_minimize_at = None

    def _proc_has_visible_window(self) -> bool:
        pid = self._current_pid()
        if not pid:
            return False
        return bool(find_window_handles_by_pid(pid))

    def _current_pid(self) -> Optional[int]:
        if self.proc and self.proc.poll() is None:
            return self.proc.pid
        return self.external_pid


class SaverWorker(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.palette_key = (self.cfg.accent_theme, self.cfg.accent_color)
        self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
        self.window = SaverWindow(self.cfg, self.palette)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(max(self.cfg.poll_sec, 0.2) * 1000))
        self.started_at = time.time()
        self.saver_visible = False

    def _tick(self):
        self.cfg = load_config()
        new_key = (self.cfg.accent_theme, self.cfg.accent_color)
        if new_key != self.palette_key:
            self.palette_key = new_key
            self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
            self.window.palette = self.palette
        self.window.cfg = self.cfg
        if not self.cfg.saver_enabled:
            if self.saver_visible:
                self.saver_visible = False
                write_notice_state(self.cfg.work_dir, saver_active=0.0)
            self.window.hide()
            return
        if time.time() - self.started_at < self.cfg.saver_start_delay_sec:
            return
        idle = seconds_since_last_input()
        if idle <= self.cfg.active_threshold_sec:
            if self.saver_visible:
                self.saver_visible = False
                write_notice_state(self.cfg.work_dir, saver_active=0.0)
            self.window.hide()
        elif idle >= self.cfg.idle_to_show_sec:
            if not self.window.isVisible():
                if not self.saver_visible:
                    self.saver_visible = True
                    write_notice_state(
                        self.cfg.work_dir,
                        saver_active=1.0,
                        saver_trigger_at=time.time(),
                    )
                self.window.show_fullscreen()
                if not self.saver_visible:
                    self.saver_visible = True
                    write_notice_state(
                        self.cfg.work_dir,
                        saver_active=1.0,
                        saver_trigger_at=time.time(),
                    )
        if self.window.isVisible():
            self.window.refresh()


def run_audio_worker():
    ensure_streams()
    cfg = load_config()
    lock_path = acquire_worker_lock(cfg.work_dir, "audio_worker")
    if not lock_path:
        log("AUDIO worker already running; exit.")
        return
    atexit.register(release_worker_lock, lock_path)
    try:
        AudioWorker().run()
    finally:
        release_worker_lock(lock_path)


def run_target_worker():
    ensure_streams()
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    worker = TargetWorker()
    app.aboutToQuit.connect(worker.notice.close)
    app.exec()


def run_saver_worker():
    ensure_streams()
    app = QtWidgets.QApplication(sys.argv)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    worker = SaverWorker()
    app.aboutToQuit.connect(worker.window.close)
    app.exec()


def run_ui():
    ensure_streams()
    app = QtWidgets.QApplication(sys.argv)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    window.hide()
    QtCore.QTimer.singleShot(0, window._start_workers)
    app.exec()


def main():
    ensure_streams()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["ui", "audio", "target", "saver"], default="ui")
    args = parser.parse_args()

    if args.mode == "audio":
        run_audio_worker()
    elif args.mode == "target":
        run_target_worker()
    elif args.mode == "saver":
        run_saver_worker()
    else:
        run_ui()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        sys.exit(0)
    except Exception as exc:
        try:
            log(f"FATAL: {exc}")
        except Exception:
            pass
        sys.exit(1)
