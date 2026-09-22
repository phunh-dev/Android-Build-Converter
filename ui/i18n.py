"""Minimal bilingual (vi/en) string table.

Not using Qt's .ts/.qm translation system — it's overkill for ~80 strings.
Instead a flat dict keyed by string id, with a global "current language"
that widgets re-read from when the user flips the language toggle.

Raw bundletool log output is deliberately NOT translated (kept in English)
so it stays useful for troubleshooting / bug reports against upstream.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

LANG_VI = "vi"
LANG_EN = "en"

_STRINGS: dict[str, tuple[str, str]] = {
    "app.title": ("Android Build Converter", "Android Build Converter"),
    "app.subtitle": (
        "Chuyển AAB sang APK universal đã ký",
        "Convert an AAB into a signed universal APK",
    ),
    "drop.aab.placeholder": ("Thả file .aab vào đây\nhoặc bấm để chọn", "Drop an .aab file here\nor click to browse"),
    "drop.aab.tooltip": (
        "Kéo-thả file Android App Bundle (.aab) vào đây, hoặc bấm để mở hộp thoại chọn file.",
        "Drag & drop an Android App Bundle (.aab) here, or click to browse.",
    ),
    "drop.keystore.placeholder": (
        "Thả file keystore vào đây\nhoặc bấm để chọn (tùy chọn)",
        "Drop a keystore file here\nor click to browse (optional)",
    ),
    "drop.keystore.tooltip": (
        "Kéo-thả file keystore (.jks/.keystore/.p12) để ký APK. "
        "Bỏ trống thì bundletool sẽ dùng debug keystore — APK không upload lên Play Store được.",
        "Drag & drop a keystore file (.jks/.keystore/.p12) to sign the APK. "
        "Leave empty and bundletool falls back to the debug keystore — the APK won't be Play Store-uploadable.",
    ),
    "field.alias.label": ("Alias:", "Alias:"),
    "field.alias.tooltip": (
        "Tên alias của key trong keystore. Không nhớ? Chọn keystore trước — danh sách alias sẽ tự điền vào đây.",
        "The key alias inside the keystore. Not sure? Pick the keystore first — the alias list fills in automatically.",
    ),
    "field.ks_password.label": ("Mật khẩu keystore:", "Keystore password:"),
    "field.ks_password.tooltip": (
        "Mật khẩu của file keystore. Không bao giờ được lưu ra đĩa ở dạng chữ thường — chỉ dùng tạm thời khi build.",
        "The keystore file's password. Never persisted to disk in plaintext — used only transiently during the build.",
    ),
    "field.key_password.label": ("Mật khẩu key:", "Key password:"),
    "field.key_password.tooltip": (
        "Mật khẩu của key (có thể khác mật khẩu keystore). Nếu không chắc, thử dùng cùng giá trị với mật khẩu keystore.",
        "The key's own password (can differ from the keystore password). If unsure, try the same value as the keystore password.",
    ),
    "field.show_password.tooltip": ("Hiện/ẩn mật khẩu", "Show/hide password"),
    "field.delete_intermediate.label": ("Xóa file .apks trung gian sau khi xong", "Delete intermediate .apks file when done"),
    "field.delete_intermediate.tooltip": (
        "bundletool tạo ra file .apks trung gian trước khi trích xuất APK. "
        "Bật tùy chọn này để thư mục output chỉ còn lại APK và log.",
        "bundletool produces an intermediate .apks file before the APK is extracted. "
        "Enable this so the output folder only keeps the APK and the log.",
    ),
    "button.convert": ("Chuyển đổi", "Convert"),
    "button.convert.tooltip": (
        "Chạy bundletool để build và ký APK universal.",
        "Run bundletool to build and sign the universal APK.",
    ),
    "button.cancel": ("Hủy", "Cancel"),
    "button.cancel.tooltip": ("Dừng quá trình đang chạy.", "Stop the running process."),
    "button.open_folder": ("Mở thư mục", "Open folder"),
    "button.open_folder.tooltip": ("Mở thư mục chứa kết quả trong File Explorer.", "Open the output folder in the file manager."),
    "button.install_device": ("Cài lên thiết bị", "Install on device"),
    "button.install_device.tooltip.ready": (
        "Cài APK vừa build lên thiết bị Android đang chọn.",
        "Install the freshly built APK on the selected Android device.",
    ),
    "button.install_device.tooltip.no_device": (
        "Chưa phát hiện thiết bị nào — bật USB debugging và cắm máy.",
        "No device detected — enable USB debugging and plug in your phone.",
    ),
    "button.refresh_devices": ("Làm mới", "Refresh"),
    "button.bundle_info": ("Thông tin", "Info"),
    "button.bundle_info.tooltip": (
        "Xem package name, versionCode, versionName, minSdk/targetSdk từ file AAB.",
        "View package name, versionCode, versionName, minSdk/targetSdk from the AAB.",
    ),
    "button.estimate_size": ("Ước tính dung lượng tải", "Estimate download size"),
    "button.estimate_size.tooltip": (
        "Build tạm ở chế độ split để ước tính dung lượng tải min/max, và kiểm tra base module "
        "có vượt giới hạn 200MB của Google Play không.",
        "Runs a temporary split-mode build to estimate min/max download size, and checks whether "
        "the base module exceeds Google Play's 200MB limit.",
    ),
    "button.build_for_device": ("Build theo thiết bị đang cắm", "Build for connected device"),
    "button.build_for_device.tooltip": (
        "Build APK tối ưu riêng cho thiết bị đang cắm — nhẹ hơn universal nhiều.",
        "Build an APK optimized for the connected device — much smaller than universal.",
    ),
    "status.java.ok": ("Java {version} ✓", "Java {version} ✓"),
    "status.java.missing": ("Chưa tìm thấy Java", "Java not found"),
    "status.adb.ok": ("adb ✓", "adb ✓"),
    "status.adb.missing": ("adb: chưa tìm thấy", "adb: not found"),
    "status.choose_java": ("Chọn đường dẫn Java…", "Choose Java path…"),
    "status.download_jdk": ("Tải JDK", "Download JDK"),
    "log.title": ("Log", "Log"),
    "log.copy": ("Sao chép", "Copy"),
    "log.save": ("Lưu log", "Save log"),
    "warning.debug_signed": (
        "⚠ APK ký bằng debug key — không upload lên Play Store được, cũng không cài đè lên bản release đã có.",
        "⚠ APK is debug-signed — cannot be uploaded to Play Store or overwrite an existing release install.",
    ),
    "success.done": ("✓ Hoàn tất: {path}", "✓ Done: {path}"),
    "size.base_module.ok": (
        "✓ Base module: {size:.1f} MB (giới hạn Play Store: {limit:.0f} MB)",
        "✓ Base module: {size:.1f} MB (Play Store limit: {limit:.0f} MB)",
    ),
    "size.base_module.over_limit": (
        "⚠ Base module {size:.1f} MB VƯỢT giới hạn {limit:.0f} MB của Google Play — "
        "build sẽ bị từ chối khi upload. Cân nhắc dùng Play Feature Delivery / asset pack.",
        "⚠ Base module is {size:.1f} MB, OVER Google Play's {limit:.0f} MB limit — "
        "the upload will be rejected. Consider Play Feature Delivery / asset packs.",
    ),
    "error.generic": ("✗ Có lỗi xảy ra, xem log bên dưới.", "✗ Something went wrong, see the log below."),
}


class Translator(QObject):
    """Holds the current language and notifies listeners on change."""

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        settings = QSettings("AndroidBuildConverter", "AndroidBuildConverter")
        self._lang = settings.value("language", LANG_VI)
        if self._lang not in (LANG_VI, LANG_EN):
            self._lang = LANG_VI

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        if lang not in (LANG_VI, LANG_EN) or lang == self._lang:
            return
        self._lang = lang
        settings = QSettings("AndroidBuildConverter", "AndroidBuildConverter")
        settings.setValue("language", lang)
        self.language_changed.emit(lang)

    def toggle(self) -> None:
        self.set_language(LANG_EN if self._lang == LANG_VI else LANG_VI)

    def t(self, key: str, **kwargs) -> str:
        pair = _STRINGS.get(key)
        if pair is None:
            return key
        text = pair[0] if self._lang == LANG_VI else pair[1]
        return text.format(**kwargs) if kwargs else text


# Module-level singleton — simplest option for a single-window desktop app.
translator = Translator()
t = translator.t
