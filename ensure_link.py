import argparse
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict
import hashlib
import json
import os
import shutil
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

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
# ==========================================


def config_file_path(work_dir: str) -> str:
    return os.path.join(work_dir, "config.json")


def log(msg: str) -> None:
    os.makedirs(WORK_DIR, exist_ok=True)
    path = os.path.join(WORK_DIR, "autowake.log")
    with open(path, "a", encoding="utf-8") as file:
        file.write(f"{datetime.now()} - {msg}\n")


def ensure_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


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
    audio_url: str = DEFAULT_AUDIO_URL
    audio_enabled: bool = True
    audio_window_mode: str = "minimized"
    audio_start_delay_sec: float = 2.0
    audio_relaunch_cooldown_sec: float = 10.0
    target_enabled: bool = True
    target_window_mode: str = "fullscreen"
    target_start_delay_sec: float = 1.0
    target_relaunch_cooldown_sec: float = 10.0
    target_refocus_interval_sec: float = 3.0
    saver_start_delay_sec: float = 1.0
    notice_enabled: bool = True
    admin_password: str = ""
    password_hash: str = ""
    password_salt: str = ""
    accent_theme: str = "sky"
    accent_color: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        chrome_fullscreen = bool(data.get("chrome_fullscreen", True))
        chrome_kiosk = bool(data.get("chrome_kiosk", False))
        inferred_mode = "fullscreen" if chrome_fullscreen else "normal"
        if chrome_kiosk:
            inferred_mode = "kiosk"

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
            chrome_fullscreen=chrome_fullscreen,
            chrome_kiosk=chrome_kiosk,
            saver_enabled=bool(data.get("saver_enabled", True)),
            chrome_repeat=bool(data.get("chrome_repeat", True)),
            ui_theme="accent",
            saver_image_mode=str(data.get("saver_image_mode", "bundled")),
            audio_url=data.get("audio_url", DEFAULT_AUDIO_URL),
            audio_enabled=bool(data.get("audio_enabled", True)),
            audio_window_mode=data.get("audio_window_mode", "minimized"),
            audio_start_delay_sec=float(data.get("audio_start_delay_sec", 2.0)),
            audio_relaunch_cooldown_sec=float(
                data.get("audio_relaunch_cooldown_sec", 10.0)
            ),
            target_enabled=bool(data.get("target_enabled", True)),
            target_window_mode=data.get("target_window_mode", inferred_mode),
            target_start_delay_sec=float(data.get("target_start_delay_sec", 1.0)),
            target_relaunch_cooldown_sec=float(
                data.get("target_relaunch_cooldown_sec", 10.0)
            ),
            target_refocus_interval_sec=float(
                data.get("target_refocus_interval_sec", 3.0)
            ),
            saver_start_delay_sec=float(data.get("saver_start_delay_sec", 1.0)),
            notice_enabled=bool(data.get("notice_enabled", True)),
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
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    return "chrome"


def build_chrome_args(url: str, profile_dir: str, mode: str, autoplay: bool) -> list[str]:
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
    mode = (mode or "normal").lower()
    if mode == "minimized":
        args.append("--start-minimized")
    elif mode == "fullscreen":
        args.append("--start-fullscreen")
    elif mode == "kiosk":
        args.append("--kiosk")
    args.append(url)
    return args


def ensure_youtube_autoplay(url: str) -> str:
    if "youtube.com" not in url and "youtu.be" not in url:
        return url
    if "autoplay=" in url:
        return url
    connector = "&" if "?" in url else "?"
    return f"{url}{connector}autoplay=1&mute=0&playsinline=1"


def launch_chrome(url: str, profile_dir: str, mode: str, autoplay: bool) -> Optional[subprocess.Popen]:
    args = build_chrome_args(url, profile_dir, mode, autoplay)
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


def build_notice_message() -> str:
    return (
        "한국기술교육대학교 참고자료실 도서 검색 전용 PC입니다.\n\n"
        "현재 사용자님을 위하여 대학 도서관 페이지의 통합검색 화면을 기본 창으로 제공하고 있습니다. "
        "본 PC는 학습·연구 목적의 정보 탐색을 돕기 위해 운영되며, 규정과 보편적 절차를 준수하는 "
        "올바른 사용을 권장드립니다. 부적절한 사용이 적발될 경우 관련 규정에 따라 안내 및 조치가 "
        "이루어질 수 있습니다.\n\n"
        "사용자님께 도움이 되었으면 좋겠습니다. 방문해 주셔서 진심으로 감사합니다.\n\n"
        "[전체화면/키오스크 종료 방법] \n"
        "- F11 키로 전체화면을 해제할 수 있습니다.\n"
        "- ESC 키를 길게 누르면 일부 전체화면이 해제될 수 있습니다.\n"
        "- Alt + F4 키로 크롬을 종료할 수 있습니다.\n\n"
        "크롬이 종료되면 몇 초 후 자동으로 다시 실행됩니다. "
        "계속 이용을 원하시면 크롬 창을 종료하지 않고 사용해 주세요.\n"
    )


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

        self.minus_button = QtWidgets.QPushButton("◀")
        self.minus_button.setObjectName("StepperButton")
        self.plus_button = QtWidgets.QPushButton("▶")
        self.plus_button.setObjectName("StepperButton")
        for button in (self.minus_button, self.plus_button):
            button.setFixedSize(24, 24)
            button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

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


class WarningDialog(QtWidgets.QDialog):
    def __init__(self, message: str, palette: dict, parent=None):
        super().__init__(parent)
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


class PasswordDialog(QtWidgets.QDialog):
    def __init__(self, verifier, palette: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("보안 확인")
        self.setModal(True)
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
        self._warning_dialog = WarningDialog(message, self._palette, self)
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
            return
        self.accept()


class PasswordChangeDialog(QtWidgets.QDialog):
    def __init__(self, palette: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("비밀번호 변경")
        self.setModal(True)
        self.setFixedSize(360, 220)
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
        layout.addWidget(QtWidgets.QLabel("현재 비밀번호와 새 비밀번호를 입력하세요."))

        form = QtWidgets.QFormLayout()
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
    def __init__(self, palette: dict, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setWindowTitle("AutoWake 안내")
        self.palette = palette
        self._build_ui()
        self.setStyleSheet(
            f"""
            #NoticeFrame {{
                background: {palette['bg_card']};
                border-radius: 16px;
                border: 1px solid {palette['border']};
            }}
            #NoticeTitle {{
                color: {palette['text_primary']};
                font-size: 18px;
                font-weight: 700;
            }}
            #NoticeMessage {{
                color: {palette['text_muted']};
            }}
            """
        )

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        frame = QtWidgets.QFrame()
        frame.setObjectName("NoticeFrame")
        frame_layout = QtWidgets.QVBoxLayout(frame)
        title = QtWidgets.QLabel("이용 안내")
        title.setObjectName("NoticeTitle")
        message = QtWidgets.QLabel(build_notice_message())
        message.setWordWrap(True)
        message.setObjectName("NoticeMessage")
        frame_layout.addWidget(title)
        frame_layout.addWidget(message)
        layout.addWidget(frame)

    def show_centered(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 800, 600)
        width = int(geometry.width() * 0.4)
        height = int(geometry.height() * 0.55)
        self.setGeometry(
            geometry.center().x() - width // 2,
            geometry.center().y() - height // 2,
            width,
            height,
        )
        self.show()


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
            geometry = screen.geometry()
            scaled = pixmap.scaled(
                geometry.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
        else:
            scaled = pixmap
        self.label.setPixmap(scaled)

    def show_fullscreen(self):
        self.refresh()
        self.showFullScreen()


class ProcessManager:
    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}

    def start(self, mode: str):
        if mode in self.processes and self.processes[mode].poll() is None:
            return
        args = [sys.executable, os.path.abspath(__file__), "--mode", mode]
        proc = subprocess.Popen(args)
        self.processes[mode] = proc
        log(f"Spawned worker: {mode}")

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
                min-width: 24px;
                min-height: 24px;
                padding: 0px;
                font-size: 14px;
                font-weight: 700;
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
            #NoticeMessage {{ color: {palette['text_muted']}; }}
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
        self.resize(700, 580)
        self.setMinimumSize(660, 560)
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

        tabs.addTab(audio_tab, "음원 옵션")
        tabs.addTab(target_tab, "URL 옵션")
        tabs.addTab(saver_tab, "스크린 세이버 옵션")
        tabs.addTab(settings_tab, "프로그램 설정")

        main_layout.addWidget(tabs)
        self.setCentralWidget(central)

    def _build_audio_section(self, layout: QtWidgets.QVBoxLayout):
        self.audio_enabled = StyledToggle("음원 사용")
        self._register_toggle(self.audio_enabled)
        layout.addWidget(self.audio_enabled)

        form = QtWidgets.QFormLayout()
        self.audio_url = QtWidgets.QLineEdit()
        self.audio_mode = ModeSelector(
            ["minimized", "normal", "fullscreen", "kiosk"],
            labels={"minimized": "최소화", "normal": "일반 창", "fullscreen": "전체화면", "kiosk": "키오스크"},
        )
        self.audio_start_delay = StepperInput()
        self.audio_start_delay.setRange(0.0, 60.0)
        self.audio_start_delay.setSingleStep(0.5)
        self.audio_start_delay.setDecimals(2)
        self.audio_relaunch_cooldown = StepperInput()
        self.audio_relaunch_cooldown.setRange(1.0, 600.0)
        self.audio_relaunch_cooldown.setSingleStep(1.0)
        self.audio_relaunch_cooldown.setDecimals(2)
        form.addRow(self._label("음원 URL"), self.audio_url)
        form.addRow(self._label("시작 창 모드"), self.audio_mode)
        form.addRow(self._label("시작 지연(초)"), self.audio_start_delay)
        form.addRow(self._label("재실행 쿨다운(초)"), self.audio_relaunch_cooldown)
        layout.addLayout(form)

    @staticmethod
    def _label(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("FormLabel")
        return label

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
        self.target_mode = ModeSelector(
            ["normal", "fullscreen", "kiosk", "minimized"],
            labels={"minimized": "최소화", "normal": "일반 창", "fullscreen": "전체화면", "kiosk": "키오스크"},
        )
        self.target_start_delay = StepperInput()
        self.target_start_delay.setRange(0.0, 60.0)
        self.target_start_delay.setSingleStep(0.5)
        self.target_start_delay.setDecimals(2)
        self.target_relaunch_cooldown = StepperInput()
        self.target_relaunch_cooldown.setRange(1.0, 600.0)
        self.target_relaunch_cooldown.setSingleStep(1.0)
        self.target_relaunch_cooldown.setDecimals(2)
        self.target_refocus_interval = StepperInput()
        self.target_refocus_interval.setRange(1.0, 60.0)
        self.target_refocus_interval.setSingleStep(1.0)
        self.target_refocus_interval.setDecimals(2)
        form.addRow(self._label("URL"), self.target_url)
        form.addRow(self._label("시작 창 모드"), self.target_mode)
        form.addRow(self._label("시작 지연(초)"), self.target_start_delay)
        form.addRow(self._label("재실행 쿨다운(초)"), self.target_relaunch_cooldown)
        form.addRow(self._label("재포커스 간격(초)"), self.target_refocus_interval)
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
        self.saver_path_label = self._label("이미지 경로")
        form.addRow(self.saver_path_label, self.saver_path_row)
        form.addRow(self._label("표시 대기(초)"), self.saver_idle_delay)
        form.addRow(self._label("활동 감지 임계(초)"), self.saver_active_threshold)
        form.addRow(self._label("폴링 주기(초)"), self.saver_poll)
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

        form = QtWidgets.QFormLayout()
        self.accent_color_button = QtWidgets.QPushButton("변경")
        self.accent_color_button.setObjectName("ThemeColorButton")
        self.accent_color_button.clicked.connect(self._open_accent_color_dialog)
        self.accent_color_button.setFixedWidth(140)
        self.chrome_relaunch_cooldown = StepperInput()
        self.chrome_relaunch_cooldown.setRange(1.0, 600.0)
        self.chrome_relaunch_cooldown.setSingleStep(1.0)
        self.chrome_relaunch_cooldown.setDecimals(2)
        form.addRow(self._label("테마 색상"), self.accent_color_button)
        form.addRow(self._label("공통 쿨다운(초)"), self.chrome_relaunch_cooldown)
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
        except Exception as exc:
            log(f"CHANGE work dir error: {exc}")

    def _ensure_default_password(self):
        if not self.cfg.password_hash:
            self.cfg.password_hash, self.cfg.password_salt = create_password_hash("0000")
            self.cfg.admin_password = ""
            save_config(self.cfg)

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
        self.showNormal()
        self.raise_()
        self.activateWindow()

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
        self._password_dialog = PasswordDialog(self._verify_password, self.palette, self)
        self._password_dialog.finished.connect(self._handle_password_finished)
        self._password_dialog.open()
        self._bring_dialog_to_front(self._password_dialog)

    def _verify_password(self, value: str) -> bool:
        return verify_password(value, self.cfg.password_hash, self.cfg.password_salt)

    def _handle_password_finished(self, result: int) -> None:
        if result == QtWidgets.QDialog.Accepted:
            self.showNormal()
            self.resize(self.minimumSize())
            self.raise_()
            self.activateWindow()
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
        self.audio_url.setText(cfg.audio_url)
        self.audio_mode.setCurrentText(cfg.audio_window_mode)
        self.audio_start_delay.setValue(cfg.audio_start_delay_sec)
        self.audio_relaunch_cooldown.setValue(cfg.audio_relaunch_cooldown_sec)

        self.target_enabled.setChecked(cfg.target_enabled)
        self.target_url.setText(cfg.url)
        self.target_mode.setCurrentText(cfg.target_window_mode)
        self.target_start_delay.setValue(cfg.target_start_delay_sec)
        self.target_relaunch_cooldown.setValue(cfg.target_relaunch_cooldown_sec)
        self.target_refocus_interval.setValue(cfg.target_refocus_interval_sec)

        self.saver_enabled.setChecked(cfg.saver_enabled)
        self.saver_mode.setCurrentText(cfg.saver_image_mode)
        self.saver_image_path.setText(cfg.image_path)
        self._update_saver_path_controls(cfg.saver_image_mode)
        self.saver_idle_delay.setValue(cfg.idle_to_show_sec)
        self.saver_active_threshold.setValue(cfg.active_threshold_sec)
        self.saver_poll.setValue(cfg.poll_sec)
        self.saver_start_delay.setValue(cfg.saver_start_delay_sec)

        self.notice_enabled.setChecked(cfg.notice_enabled)
        self._update_accent_color_button(cfg.accent_color or self.palette["accent"])
        self.chrome_relaunch_cooldown.setValue(cfg.chrome_relaunch_cooldown_sec)
        self.config_path.setText(cfg.work_dir)
        self._update_run_state_labels()
        self._loading = False

    def _gather_config(self) -> AppConfig:
        target_mode = self.target_mode.currentText()
        cfg = AppConfig(
            url=self.target_url.text(),
            image_path=self.saver_image_path.text(),
            work_dir=self.cfg.work_dir,
            idle_to_show_sec=self.saver_idle_delay.value(),
            active_threshold_sec=self.saver_active_threshold.value(),
            poll_sec=self.saver_poll.value(),
            chrome_relaunch_cooldown_sec=self.chrome_relaunch_cooldown.value(),
            chrome_fullscreen=target_mode in {"fullscreen", "kiosk"},
            chrome_kiosk=target_mode == "kiosk",
            saver_enabled=self.saver_enabled.isChecked(),
            chrome_repeat=self.cfg.chrome_repeat,
            ui_theme="accent",
            saver_image_mode=self.saver_mode.currentText(),
            audio_url=self.audio_url.text(),
            audio_enabled=self.audio_enabled.isChecked(),
            audio_window_mode=self.audio_mode.currentText(),
            audio_start_delay_sec=self.audio_start_delay.value(),
            audio_relaunch_cooldown_sec=self.audio_relaunch_cooldown.value(),
            target_enabled=self.target_enabled.isChecked(),
            target_window_mode=target_mode,
            target_start_delay_sec=self.target_start_delay.value(),
            target_relaunch_cooldown_sec=self.target_relaunch_cooldown.value(),
            target_refocus_interval_sec=self.target_refocus_interval.value(),
            saver_start_delay_sec=self.saver_start_delay.value(),
            notice_enabled=self.notice_enabled.isChecked(),
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
            self.audio_url,
            self.saver_image_path,
            self.target_url,
        ]:
            widget.textEdited.connect(self._autosave)
        for widget in [
            self.audio_mode,
            self.target_mode,
            self.saver_mode,
        ]:
            widget.currentTextChanged.connect(self._autosave)
        for widget in [
            self.audio_start_delay,
            self.audio_relaunch_cooldown,
            self.target_start_delay,
            self.target_relaunch_cooldown,
            self.target_refocus_interval,
            self.saver_idle_delay,
            self.saver_active_threshold,
            self.saver_poll,
            self.saver_start_delay,
            self.chrome_relaunch_cooldown,
        ]:
            widget.valueChanged.connect(self._autosave)

    def _autosave(self, *_args):
        if getattr(self, "_loading", False):
            return
        self._save_config()

    def _start_workers(self):
        self._save_config()
        cfg = self.cfg
        if self.is_running:
            return
        if cfg.audio_enabled:
            self.process_manager.start("audio")
        if cfg.target_enabled:
            self.process_manager.start("target")
        if cfg.saver_enabled:
            self.process_manager.start("saver")
        self.is_running = True
        self._update_run_state_labels()

    def _stop_workers(self):
        self.process_manager.stop_all()
        self.is_running = False
        self._update_run_state_labels()

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
        self.last_launch = 0.0
        self.pending_launch_at: Optional[float] = None
        self.last_config_signature: Optional[tuple] = None

    def run(self):
        while True:
            self.cfg = load_config()
            config_signature = (
                self.cfg.audio_url,
                self.cfg.audio_window_mode,
                self.cfg.audio_start_delay_sec,
                self.cfg.audio_relaunch_cooldown_sec,
                self.cfg.audio_enabled,
            )
            if self.last_config_signature is None:
                self.last_config_signature = config_signature
            elif config_signature != self.last_config_signature:
                self.last_config_signature = config_signature
                if self.proc and self.proc.poll() is None:
                    self._stop_proc()
                    self.pending_launch_at = time.time() + self.cfg.audio_start_delay_sec
                    self.last_launch = 0.0
            if not self.cfg.audio_enabled:
                self._stop_proc()
                self.pending_launch_at = None
                time.sleep(self.cfg.poll_sec)
                continue
            if self.proc is None or self.proc.poll() is not None:
                now = time.time()
                if now - self.last_launch >= self.cfg.audio_relaunch_cooldown_sec:
                    if self.pending_launch_at is None:
                        self.pending_launch_at = now + self.cfg.audio_start_delay_sec
            if self.pending_launch_at is not None:
                now = time.time()
                if now >= self.pending_launch_at:
                    url = ensure_youtube_autoplay(self.cfg.audio_url)
                    profile = os.path.join(self.cfg.work_dir, "chrome_profiles", "audio")
                    os.makedirs(profile, exist_ok=True)
                    self.proc = launch_chrome(url, profile, self.cfg.audio_window_mode, True)
                    self.last_launch = time.time()
                    self.pending_launch_at = None
            time.sleep(max(self.cfg.poll_sec, 0.2))

    def _stop_proc(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None


class TargetWorker(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.proc: Optional[subprocess.Popen] = None
        self.last_launch = 0.0
        self.last_refocus = 0.0
        self.pending_launch_at: Optional[float] = None
        self.last_config_signature: Optional[tuple] = None
        self.palette_key = (self.cfg.accent_theme, self.cfg.accent_color)
        self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
        self.notice = NoticeWindow(self.palette)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(max(self.cfg.poll_sec, 0.2) * 1000))

    def _tick(self):
        self.cfg = load_config()
        config_signature = (
            self.cfg.url,
            self.cfg.target_window_mode,
            self.cfg.target_start_delay_sec,
            self.cfg.target_relaunch_cooldown_sec,
            self.cfg.target_enabled,
        )
        if self.last_config_signature is None:
            self.last_config_signature = config_signature
        elif config_signature != self.last_config_signature:
            self.last_config_signature = config_signature
            if self.proc and self.proc.poll() is None:
                self._stop_proc()
                self.pending_launch_at = time.time() + self.cfg.target_start_delay_sec
                self.last_launch = 0.0
        new_key = (self.cfg.accent_theme, self.cfg.accent_color)
        if new_key != self.palette_key:
            self.palette_key = new_key
            self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
            self.notice.palette = self.palette
            self.notice.setStyleSheet(
                f"""
                #NoticeFrame {{
                    background: {self.palette['bg_card']};
                    border-radius: 16px;
                    border: 1px solid {self.palette['border']};
                }}
                #NoticeTitle {{
                    color: {self.palette['text_primary']};
                    font-size: 18px;
                    font-weight: 700;
                }}
                #NoticeMessage {{
                    color: {self.palette['text_muted']};
                }}
                """
            )
        if self.cfg.notice_enabled and self.cfg.target_enabled:
            if not self.notice.isVisible():
                self.notice.show_centered()
        else:
            self.notice.hide()

        if not self.cfg.target_enabled:
            self._stop_proc()
            self.pending_launch_at = None
            return

        if self.proc is None or self.proc.poll() is not None:
            now = time.time()
            if now - self.last_launch >= self.cfg.target_relaunch_cooldown_sec:
                if self.pending_launch_at is None:
                    self.pending_launch_at = now + self.cfg.target_start_delay_sec

        if self.pending_launch_at is not None:
            now = time.time()
            if now >= self.pending_launch_at:
                profile = os.path.join(self.cfg.work_dir, "chrome_profiles", "target")
                os.makedirs(profile, exist_ok=True)
                self.proc = launch_chrome(
                    self.cfg.url,
                    profile,
                    self.cfg.target_window_mode,
                    False,
                )
                self.last_launch = time.time()
                self.pending_launch_at = None

        if self.proc and self.proc.poll() is None:
            now = time.time()
            if now - self.last_refocus >= self.cfg.target_refocus_interval_sec:
                keep_window_on_top(self.proc.pid)
                self.last_refocus = now

    def _stop_proc(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None


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

    def _tick(self):
        self.cfg = load_config()
        new_key = (self.cfg.accent_theme, self.cfg.accent_color)
        if new_key != self.palette_key:
            self.palette_key = new_key
            self.palette = build_palette(self.cfg.accent_theme, self.cfg.accent_color)
            self.window.palette = self.palette
        self.window.cfg = self.cfg
        if not self.cfg.saver_enabled:
            self.window.hide()
            return
        if time.time() - self.started_at < self.cfg.saver_start_delay_sec:
            return
        idle = seconds_since_last_input()
        if idle <= self.cfg.active_threshold_sec:
            self.window.hide()
        elif idle >= self.cfg.idle_to_show_sec:
            if not self.window.isVisible():
                self.window.show_fullscreen()
        if self.window.isVisible():
            self.window.refresh()


def run_audio_worker():
    ensure_streams()
    AudioWorker().run()


def run_target_worker():
    ensure_streams()
    app = QtWidgets.QApplication(sys.argv)
    worker = TargetWorker()
    app.aboutToQuit.connect(worker.notice.close)
    app.exec()


def run_saver_worker():
    ensure_streams()
    app = QtWidgets.QApplication(sys.argv)
    worker = SaverWorker()
    app.aboutToQuit.connect(worker.window.close)
    app.exec()


def run_ui():
    ensure_streams()
    app = QtWidgets.QApplication(sys.argv)
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
