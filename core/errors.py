"""Map raw bundletool stderr messages to friendly bilingual summaries.

Source strings verified by decompiling bundletool 1.18.3's SignerConfig.class
(see the project plan for the full provenance). These are matched with
substring checks because bundletool prefixes them with "[BT:<version>] Error: "
and sometimes appends extra detail.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FriendlyError:
    key: str
    vi: str
    en: str


# Ordered: more specific patterns first, since some messages are substrings
# of others (e.g. "Incorrect key password." vs "Incorrect keystore password.").
_PATTERNS: list[tuple[str, FriendlyError]] = [
    (
        "Incorrect keystore password.",
        FriendlyError(
            key="wrong_keystore_password",
            vi="Sai mật khẩu keystore.",
            en="Incorrect keystore password.",
        ),
    ),
    (
        "Incorrect key password.",
        FriendlyError(
            key="wrong_key_password",
            vi="Sai mật khẩu key (khác mật khẩu keystore).",
            en="Incorrect key password (different from the keystore password).",
        ),
    ),
    (
        "No key found with alias",
        FriendlyError(
            key="alias_not_found",
            vi="Không tìm thấy alias trong keystore — kiểm tra lại danh sách alias.",
            en="Alias not found in the keystore — check the alias list.",
        ),
    ),
    (
        "Unable to build a keystore instance",
        FriendlyError(
            key="corrupt_keystore",
            vi="File keystore hỏng hoặc sai định dạng.",
            en="The keystore file is corrupt or in an unsupported format.",
        ),
    ),
    (
        "Error while loading private key and certificates from the keystore",
        FriendlyError(
            key="keystore_load_failed",
            vi="Không đọc được private key/chứng chỉ từ keystore.",
            en="Failed to load the private key/certificates from the keystore.",
        ),
    ),
    (
        "Unable to make aapt2 executable",
        FriendlyError(
            key="aapt2_permission",
            vi="Bị chặn quyền/antivirus khi giải nén aapt2 — thử chạy lại hoặc đổi thư mục tạm.",
            en="Permission/antivirus blocked extracting aapt2 — retry or change the temp directory.",
        ),
    ),
    (
        "already exists",
        FriendlyError(
            key="output_exists",
            vi="File output đã tồn tại (thiếu --overwrite).",
            en="Output file already exists (missing --overwrite).",
        ),
    ),
]


def friendly_message(raw_stderr: str) -> FriendlyError | None:
    """Return a friendly bilingual summary for a known bundletool error, or
    None if the message isn't recognized (caller should fall back to showing
    the raw log)."""
    for pattern, friendly in _PATTERNS:
        if pattern in raw_stderr:
            return friendly
    return None
