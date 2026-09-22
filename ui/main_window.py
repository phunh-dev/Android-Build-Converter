"""Main application window: drop AAB + keystore, sign, convert, install."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import bundletool, devices, errors, keystore, manifest, toolchain, workflow
from core.toolchain import Toolchain
from ui.drop_zone import DropZone
from ui.i18n import t, translator
from ui.log_view import LogView

AAB_EXTENSIONS = (".aab",)
KEYSTORE_EXTENSIONS = (".jks", ".keystore", ".p12")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(t("app.title"))
        self.resize(920, 720)

        self._toolchain: Toolchain = toolchain.detect_toolchain()
        self._runner: bundletool.BundletoolRunner | None = None
        self._ks_pw_file: bundletool.TemporaryPasswordFile | None = None
        self._key_pw_file: bundletool.TemporaryPasswordFile | None = None
        self._current_layout: workflow.OutputLayout | None = None
        self._current_devices: list[devices.Device] = []

        self._build_ui()
        self._refresh_status_bar()
        translator.language_changed.connect(self._retranslate)
        if self._toolchain.adb.found:
            self._refresh_devices()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        outer.addLayout(self._build_header())
        outer.addLayout(self._build_drop_row())
        outer.addWidget(self._build_credentials_group())
        outer.addLayout(self._build_action_row())

        self._log_view = LogView()
        outer.addWidget(QLabel(t("log.title")))
        outer.addWidget(self._log_view, stretch=1)

        outer.addWidget(self._build_device_group())
        outer.addLayout(self._build_status_bar())

        self.setStyleSheet(_DARK_STYLESHEET)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._title_label = QLabel(t("app.title"))
        self._title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        self._subtitle_label = QLabel(t("app.subtitle"))
        self._subtitle_label.setStyleSheet("color: #9a9aa8;")

        title_col = QVBoxLayout()
        title_col.addWidget(self._title_label)
        title_col.addWidget(self._subtitle_label)
        row.addLayout(title_col)
        row.addStretch()

        self._lang_button = QPushButton("VI / EN")
        self._lang_button.setToolTip("Chuyển ngôn ngữ / Switch language")
        self._lang_button.clicked.connect(translator.toggle)
        row.addWidget(self._lang_button, alignment=Qt.AlignmentFlag.AlignTop)
        return row

    def _build_drop_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._aab_drop = DropZone(
            AAB_EXTENSIONS,
            t("drop.aab.placeholder"),
            "Android App Bundle (*.aab)",
        )
        self._aab_drop.setToolTip(t("drop.aab.tooltip"))
        self._aab_drop.file_selected.connect(self._on_aab_selected)

        self._keystore_drop = DropZone(
            KEYSTORE_EXTENSIONS,
            t("drop.keystore.placeholder"),
            "Keystore (*.jks *.keystore *.p12)",
        )
        self._keystore_drop.setToolTip(t("drop.keystore.tooltip"))
        self._keystore_drop.file_selected.connect(self._on_keystore_selected)

        row.addWidget(self._aab_drop, stretch=1)
        row.addWidget(self._keystore_drop, stretch=1)
        return row

    def _build_credentials_group(self) -> QGroupBox:
        self._credentials_group = QGroupBox()
        form = QFormLayout(self._credentials_group)

        self._alias_combo = QComboBox()
        self._alias_combo.setEditable(True)
        self._alias_combo.setToolTip(t("field.alias.tooltip"))
        self._alias_label = QLabel(t("field.alias.label"))
        form.addRow(self._alias_label, self._alias_combo)

        self._ks_password_edit = _password_field(t("field.ks_password.tooltip"))
        self._ks_password_label = QLabel(t("field.ks_password.label"))
        form.addRow(self._ks_password_label, self._ks_password_edit)

        self._keystore_status_label = QLabel()
        self._keystore_status_label.setStyleSheet("color: #9a9aa8; font-size: 11px;")
        form.addRow("", self._keystore_status_label)

        # Debounce keystore password checks — don't shell out to keytool on
        # every keystroke, only after the user pauses typing.
        self._keystore_check_timer = QTimer(self)
        self._keystore_check_timer.setSingleShot(True)
        self._keystore_check_timer.setInterval(500)
        self._keystore_check_timer.timeout.connect(self._check_keystore_password)
        self._ks_password_edit.textChanged.connect(lambda _: self._keystore_check_timer.start())

        self._key_password_edit = _password_field(t("field.key_password.tooltip"))
        self._key_password_label = QLabel(t("field.key_password.label"))
        form.addRow(self._key_password_label, self._key_password_edit)

        self._delete_intermediate_checkbox = QCheckBox(t("field.delete_intermediate.label"))
        self._delete_intermediate_checkbox.setChecked(True)
        self._delete_intermediate_checkbox.setToolTip(t("field.delete_intermediate.tooltip"))
        form.addRow("", self._delete_intermediate_checkbox)

        return self._credentials_group

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self._info_button = QPushButton(t("button.bundle_info"))
        self._info_button.setToolTip(t("button.bundle_info.tooltip"))
        self._info_button.setEnabled(False)
        self._info_button.clicked.connect(self._on_show_bundle_info)
        row.addWidget(self._info_button)

        row.addStretch()

        self._convert_button = QPushButton(t("button.convert"))
        self._convert_button.setToolTip(t("button.convert.tooltip"))
        self._convert_button.setObjectName("primaryButton")
        self._convert_button.clicked.connect(self._on_convert_clicked)
        row.addWidget(self._convert_button)

        self._cancel_button = QPushButton(t("button.cancel"))
        self._cancel_button.setToolTip(t("button.cancel.tooltip"))
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        row.addWidget(self._cancel_button)

        return row

    def _build_device_group(self) -> QGroupBox:
        self._device_group = QGroupBox()
        row = QHBoxLayout(self._device_group)

        self._device_combo = QComboBox()
        row.addWidget(self._device_combo, stretch=1)

        self._refresh_devices_button = QPushButton(t("button.refresh_devices"))
        self._refresh_devices_button.clicked.connect(self._refresh_devices)
        row.addWidget(self._refresh_devices_button)

        self._install_button = QPushButton(t("button.install_device"))
        self._install_button.setEnabled(False)
        self._install_button.clicked.connect(self._on_install_clicked)
        row.addWidget(self._install_button)

        self._build_for_device_button = QPushButton(t("button.build_for_device"))
        self._build_for_device_button.setToolTip(t("button.build_for_device.tooltip"))
        self._build_for_device_button.setEnabled(False)
        self._build_for_device_button.clicked.connect(self._on_build_for_device_clicked)
        row.addWidget(self._build_for_device_button)

        return self._device_group

    def _build_status_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._java_status_label = QLabel()
        self._adb_status_label = QLabel()
        row.addWidget(self._java_status_label)
        row.addWidget(self._adb_status_label)
        row.addStretch()

        self._open_folder_button = QPushButton(t("button.open_folder"))
        self._open_folder_button.setToolTip(t("button.open_folder.tooltip"))
        self._open_folder_button.setEnabled(False)
        self._open_folder_button.clicked.connect(self._on_open_folder_clicked)
        row.addWidget(self._open_folder_button)

        self._estimate_size_button = QPushButton(t("button.estimate_size"))
        self._estimate_size_button.setToolTip(t("button.estimate_size.tooltip"))
        self._estimate_size_button.setEnabled(False)
        self._estimate_size_button.clicked.connect(self._on_estimate_size_clicked)
        row.addWidget(self._estimate_size_button)

        return row

    # --------------------------------------------------------- status/i18n

    def _refresh_status_bar(self) -> None:
        java = self._toolchain.java
        if java.found:
            version = (java.version or "").split('"')[1] if java.version and '"' in java.version else ""
            self._java_status_label.setText(f"🟢 {t('status.java.ok', version=version)}")
        else:
            self._java_status_label.setText(f"🔴 {t('status.java.missing')}")
            self._convert_button.setEnabled(False)
            self._convert_button.setToolTip(t("status.java.missing"))

        adb = self._toolchain.adb
        if adb.found:
            self._adb_status_label.setText(f"🟢 {t('status.adb.ok')}")
        else:
            self._adb_status_label.setText(f"🟡 {t('status.adb.missing')}")

    def _retranslate(self, _lang: str) -> None:
        self.setWindowTitle(t("app.title"))
        self._title_label.setText(t("app.title"))
        self._subtitle_label.setText(t("app.subtitle"))
        self._aab_drop.set_placeholder_text(t("drop.aab.placeholder"))
        self._aab_drop.setToolTip(t("drop.aab.tooltip"))
        self._keystore_drop.set_placeholder_text(t("drop.keystore.placeholder"))
        self._keystore_drop.setToolTip(t("drop.keystore.tooltip"))
        self._alias_label.setText(t("field.alias.label"))
        self._alias_combo.setToolTip(t("field.alias.tooltip"))
        self._ks_password_label.setText(t("field.ks_password.label"))
        self._key_password_label.setText(t("field.key_password.label"))
        self._delete_intermediate_checkbox.setText(t("field.delete_intermediate.label"))
        self._delete_intermediate_checkbox.setToolTip(t("field.delete_intermediate.tooltip"))
        self._info_button.setText(t("button.bundle_info"))
        self._info_button.setToolTip(t("button.bundle_info.tooltip"))
        self._convert_button.setText(t("button.convert"))
        self._cancel_button.setText(t("button.cancel"))
        self._refresh_devices_button.setText(t("button.refresh_devices"))
        self._install_button.setText(t("button.install_device"))
        self._build_for_device_button.setText(t("button.build_for_device"))
        self._build_for_device_button.setToolTip(t("button.build_for_device.tooltip"))
        self._open_folder_button.setText(t("button.open_folder"))
        self._estimate_size_button.setText(t("button.estimate_size"))
        self._refresh_status_bar()

    # -------------------------------------------------------------- events

    def _on_aab_selected(self, path: str) -> None:
        self._current_layout = workflow.OutputLayout.for_bundle(path)
        self._info_button.setEnabled(True)

    def _on_keystore_selected(self, path: str) -> None:
        self._alias_combo.clear()
        self._keystore_status_label.clear()
        if self._ks_password_edit.text():
            self._check_keystore_password()

    def _check_keystore_password(self) -> None:
        """Pre-validate the keystore password + list aliases via keytool,
        turning a "wait 3 minutes then fail" build error into instant
        feedback. Key-password verification isn't possible this way (keytool
        -keypasswd doesn't support PKCS12), so only the store password and
        alias list are checked here."""
        ks_path = self._keystore_drop.selected_path
        password = self._ks_password_edit.text()
        if not ks_path or not password or not self._toolchain.keytool.found:
            self._keystore_status_label.clear()
            return

        result = keystore.list_aliases(self._toolchain.keytool.path, ks_path, password)
        if result.ok:
            current = self._alias_combo.currentText()
            self._alias_combo.clear()
            self._alias_combo.addItems(result.aliases)
            if current in result.aliases:
                self._alias_combo.setCurrentText(current)
            self._keystore_status_label.setStyleSheet("color: #5fd97f; font-size: 11px;")
            self._keystore_status_label.setText(f"✓ {len(result.aliases)} alias(es) found")
        elif result.error == "wrong_password":
            self._keystore_status_label.setStyleSheet("color: #ff8080; font-size: 11px;")
            self._keystore_status_label.setText(t("field.ks_password.label") + " ✗")
        else:
            self._keystore_status_label.clear()

    def _on_show_bundle_info(self) -> None:
        bundle_path = self._aab_drop.selected_path
        if not bundle_path or not self._toolchain.java.found:
            return

        jar_path = str(bundletool.resource_path("resources/bundletool.jar"))
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            info = manifest.read_bundle_info(self._toolchain.java.path, jar_path, bundle_path)
        finally:
            self.unsetCursor()

        if info.error:
            QMessageBox.warning(self, t("button.bundle_info"), info.error)
            return

        rows = [
            ("Package", info.package),
            ("Version code", info.version_code),
            ("Version name", info.version_name),
            ("Min SDK", info.min_sdk),
            ("Target SDK", info.target_sdk),
        ]
        text = "\n".join(f"{label}: {value or '—'}" for label, value in rows)
        QMessageBox.information(self, t("button.bundle_info"), text)

    def _on_convert_clicked(self) -> None:
        if self._aab_drop.selected_path is None or self._current_layout is None:
            return

        self._current_layout.ensure_output_dir()
        self._log_view.append_system(f"$ java -jar bundletool.jar build-apks --bundle=... --output=...")

        ks = self._keystore_drop.selected_path
        ks_password = self._ks_password_edit.text()
        key_password = self._key_password_edit.text() or ks_password
        alias = self._alias_combo.currentText().strip()

        self._ks_pw_file = bundletool.TemporaryPasswordFile(ks_password) if ks else None
        self._key_pw_file = bundletool.TemporaryPasswordFile(key_password) if ks else None

        try:
            if self._ks_pw_file:
                self._ks_pw_file.__enter__()
            if self._key_pw_file:
                self._key_pw_file.__enter__()

            args = bundletool.build_apks_args(
                bundle=self._aab_drop.selected_path,
                output=str(self._current_layout.apks_path),
                ks=ks,
                ks_pass_file=self._ks_pw_file.path if self._ks_pw_file else None,
                ks_key_alias=alias or None,
                key_pass_file=self._key_pw_file.path if self._key_pw_file else None,
            )
        except ValueError as exc:
            self._log_view.append_line(str(exc), is_stderr=True)
            self._cleanup_password_files()
            return

        if not ks:
            self._log_view.append_warning(t("warning.debug_signed"))

        jar_path = str(bundletool.resource_path("resources/bundletool.jar"))
        self._runner = bundletool.BundletoolRunner(self._toolchain.java.path, jar_path, parent=self)
        self._runner.line_output.connect(self._on_process_line)
        self._runner.finished.connect(self._on_process_finished)

        self._convert_button.setEnabled(False)
        self._cancel_button.setEnabled(True)
        self._runner.start(args)

    def _on_cancel_clicked(self) -> None:
        if self._runner:
            self._runner.cancel()

    def _on_process_line(self, line: str, is_stderr: bool) -> None:
        self._log_view.append_line(line, is_stderr=is_stderr)

    def _on_process_finished(self, exit_code: int) -> None:
        self._convert_button.setEnabled(True)
        self._cancel_button.setEnabled(False)
        self._cleanup_password_files()

        if exit_code == 0 and self._current_layout and self._current_layout.apks_path.exists():
            try:
                workflow.extract_universal_apk(self._current_layout.apks_path, self._current_layout.apk_path)
                if self._delete_intermediate_checkbox.isChecked():
                    workflow.cleanup_intermediate_apks(self._current_layout.apks_path)
                self._log_view.append_success(t("success.done", path=str(self._current_layout.apk_path)))
                self._open_folder_button.setEnabled(True)
                self._estimate_size_button.setEnabled(True)
            except workflow.UniversalApkNotFoundError as exc:
                self._log_view.append_line(str(exc), is_stderr=True)
        else:
            self._log_view.append_line(t("error.generic"), is_stderr=True)

    def _cleanup_password_files(self) -> None:
        if self._ks_pw_file:
            self._ks_pw_file.__exit__(None, None, None)
            self._ks_pw_file = None
        if self._key_pw_file:
            self._key_pw_file.__exit__(None, None, None)
            self._key_pw_file = None

    def _on_open_folder_clicked(self) -> None:
        if self._current_layout:
            workflow.open_in_file_manager(self._current_layout.output_dir)

    def _on_estimate_size_clicked(self) -> None:
        """Build a temporary split-mode .apks (universal mode reports only
        the single APK's size, which isn't meaningful for a min/max
        estimate) and run `get-size total` against it."""
        if not self._aab_drop.selected_path or not self._current_layout:
            return

        jar_path = str(bundletool.resource_path("resources/bundletool.jar"))
        split_apks_path = self._current_layout.output_dir / "_size_estimate.apks"
        self._current_layout.ensure_output_dir()

        build_args = bundletool.build_apks_args(
            bundle=self._aab_drop.selected_path,
            output=str(split_apks_path),
            mode="default",
            verbose=False,
        )

        self._log_view.append_system("$ estimating download size (split-mode build)…")
        self.setCursor(Qt.CursorShape.WaitCursor)
        self._estimate_size_button.setEnabled(False)

        self._size_runner = bundletool.BundletoolRunner(self._toolchain.java.path, jar_path, parent=self)
        self._size_runner.line_output.connect(lambda line, is_err: self._log_view.append_line(line, is_stderr=is_err))
        self._size_runner.finished.connect(lambda code: self._on_size_build_finished(code, split_apks_path))
        self._size_runner.start(build_args)

    def _on_size_build_finished(self, exit_code: int, split_apks_path) -> None:
        self.unsetCursor()
        self._estimate_size_button.setEnabled(True)

        if exit_code != 0 or not split_apks_path.exists():
            self._log_view.append_line("✗ Could not build split APKs for size estimation.", is_stderr=True)
            return

        import platform
        import subprocess

        # Base module size vs. Google Play's 200MB limit — reuses the same
        # split-mode .apks just built, no extra bundletool invocation needed.
        base_check = workflow.check_base_module_size(split_apks_path)
        if base_check.error is None and base_check.size_mb is not None:
            if base_check.over_limit:
                self._log_view.append_warning(
                    t("size.base_module.over_limit", size=base_check.size_mb, limit=base_check.limit_mb)
                )
            else:
                self._log_view.append_success(
                    t("size.base_module.ok", size=base_check.size_mb, limit=base_check.limit_mb)
                )

        jar_path = str(bundletool.resource_path("resources/bundletool.jar"))
        size_args = bundletool.build_get_size_args(apks=str(split_apks_path), dimensions="SDK,ABI,SCREEN_DENSITY")
        try:
            proc = subprocess.run(
                [self._toolchain.java.path, "-jar", jar_path, *size_args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            )
            for line in proc.stdout.splitlines():
                self._log_view.append_success(line) if proc.returncode == 0 else self._log_view.append_line(line, is_stderr=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._log_view.append_line(str(exc), is_stderr=True)
        finally:
            split_apks_path.unlink(missing_ok=True)

    def _refresh_devices(self) -> None:
        if not self._toolchain.adb.found:
            self._current_devices = []
            self._device_combo.clear()
            self._install_button.setEnabled(False)
            self._build_for_device_button.setEnabled(False)
            return

        self._current_devices = devices.list_devices(self._toolchain.adb.path)
        self._device_combo.clear()
        online = [d for d in self._current_devices if d.state == "device"]
        for d in self._current_devices:
            label = d.display_name if d.state == "device" else f"{d.display_name} [{d.state}]"
            self._device_combo.addItem(label, userData=d.serial)

        has_online_device = bool(online)
        self._install_button.setEnabled(has_online_device)
        self._build_for_device_button.setEnabled(has_online_device)
        tooltip_key = (
            "button.install_device.tooltip.ready" if has_online_device else "button.install_device.tooltip.no_device"
        )
        self._install_button.setToolTip(t(tooltip_key))

    def _selected_device_serial(self) -> str | None:
        index = self._device_combo.currentIndex()
        if index < 0:
            return None
        return self._device_combo.itemData(index)

    def _on_install_clicked(self) -> None:
        if not self._current_layout or not self._current_layout.apk_path.exists():
            return
        serial = self._selected_device_serial()
        adb_path = self._toolchain.adb.path
        if not adb_path:
            return

        self._log_view.append_system(f"$ adb install {self._current_layout.apk_path.name}")
        try:
            import platform
            import subprocess

            proc = subprocess.run(
                [adb_path, *(["-s", serial] if serial else []), "install", "-r", str(self._current_layout.apk_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            )
            for line in (proc.stdout + proc.stderr).splitlines():
                self._log_view.append_line(line, is_stderr=proc.returncode != 0)
            if proc.returncode == 0:
                self._log_view.append_success(f"✓ Installed on {serial or 'device'}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._log_view.append_line(str(exc), is_stderr=True)

    def _on_build_for_device_clicked(self) -> None:
        """Build a device-optimized (non-universal) APK: get-device-spec on
        the selected device, then build-apks --device-spec=... --mode=default.
        Much smaller than universal since it excludes unneeded ABIs/densities."""
        if not self._aab_drop.selected_path or not self._current_layout or not self._toolchain.adb.path:
            return

        serial = self._selected_device_serial()
        jar_path = str(bundletool.resource_path("resources/bundletool.jar"))
        self._current_layout.ensure_output_dir()
        spec_path = self._current_layout.output_dir / "_device-spec.json"

        spec_args = bundletool.build_get_device_spec_args(
            output=str(spec_path), adb_path=self._toolchain.adb.path, device_id=serial
        )

        self._log_view.append_system("$ get-device-spec …")
        self.setCursor(Qt.CursorShape.WaitCursor)
        self._build_for_device_button.setEnabled(False)

        self._device_spec_runner = bundletool.BundletoolRunner(self._toolchain.java.path, jar_path, parent=self)
        self._device_spec_runner.line_output.connect(
            lambda line, is_err: self._log_view.append_line(line, is_stderr=is_err)
        )
        self._device_spec_runner.finished.connect(lambda code: self._on_device_spec_finished(code, spec_path))
        self._device_spec_runner.start(spec_args)

    def _on_device_spec_finished(self, exit_code: int, spec_path) -> None:
        self._build_for_device_button.setEnabled(True)

        if exit_code != 0 or not spec_path.exists():
            self.unsetCursor()
            self._log_view.append_line("✗ Could not read connected device's spec.", is_stderr=True)
            return

        jar_path = str(bundletool.resource_path("resources/bundletool.jar"))
        device_apks_path = self._current_layout.output_dir / f"{self._current_layout.apks_path.stem}-device.apks"
        device_apk_path = self._current_layout.output_dir / f"{self._current_layout.apks_path.stem}-device.apk"

        build_args = bundletool.build_apks_args(
            bundle=self._aab_drop.selected_path,
            output=str(device_apks_path),
            mode="default",
            device_spec=str(spec_path),
            verbose=False,
        )

        self._log_view.append_system("$ building device-optimized APK…")
        self._device_build_runner = bundletool.BundletoolRunner(self._toolchain.java.path, jar_path, parent=self)
        self._device_build_runner.line_output.connect(
            lambda line, is_err: self._log_view.append_line(line, is_stderr=is_err)
        )
        self._device_build_runner.finished.connect(
            lambda code: self._on_device_build_finished(code, device_apks_path, device_apk_path, spec_path)
        )
        self._device_build_runner.start(build_args)

    def _on_device_build_finished(self, exit_code: int, apks_path, apk_path, spec_path) -> None:
        self.unsetCursor()
        spec_path.unlink(missing_ok=True)

        if exit_code != 0 or not apks_path.exists():
            self._log_view.append_line("✗ Device-optimized build failed.", is_stderr=True)
            return

        try:
            workflow.extract_universal_apk(apks_path, apk_path)
            apks_path.unlink(missing_ok=True)
            self._log_view.append_success(f"✓ Device-optimized APK: {apk_path}")
        except workflow.UniversalApkNotFoundError as exc:
            self._log_view.append_line(str(exc), is_stderr=True)


def _password_field(tooltip: str) -> QLineEdit:
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setToolTip(tooltip)
    return edit


_DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e24;
    color: #e4e4ec;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #3a3a44;
    border-radius: 8px;
    margin-top: 8px;
    padding: 8px;
}
QLineEdit, QComboBox {
    background-color: #2b2b33;
    border: 1px solid #4a4a55;
    border-radius: 6px;
    padding: 6px 8px;
}
QPushButton {
    background-color: #33333d;
    border: 1px solid #4a4a55;
    border-radius: 6px;
    padding: 7px 14px;
}
QPushButton:hover:!disabled {
    background-color: #3d3d48;
}
QPushButton:disabled {
    color: #6a6a76;
}
QPushButton#primaryButton {
    background-color: #3f6fdb;
    border: none;
    font-weight: 600;
}
QPushButton#primaryButton:hover:!disabled {
    background-color: #4a7bea;
}
QCheckBox {
    spacing: 8px;
}
"""
