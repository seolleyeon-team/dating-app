#!/usr/bin/env python3
"""Android release 서명 상태 점검 (secret 미출력).

release 빌드가 "성공"했다는 것만으로는 스토어에 올릴 수 있는지 알 수 없다.
이 프로젝트의 Gradle 설정은 `android/key.properties` 가 있을 때만 release 서명을
붙이고 없으면 **서명 없이** 빌드된다 (debug 키로 대체하지 않는다). 그래서 빌드
로그만 보면 서명되지 않은 산출물을 서명된 것으로 착각하기 쉽다.

이 스크립트가 확인하는 것:

    1. key.properties 가 있는지, 필요한 키가 모두 있는지 (값은 읽어서 출력하지 않는다)
    2. storeFile 이 실제로 존재하는지
    3. 주어진 AAB/APK 가 서명돼 있는지
    4. 서명 인증서의 공개 지문(SHA-1 / SHA-256)
    5. 그 인증서가 **디버그 인증서가 아닌지** — 실수로 디버그 서명본을 올리는 것을 막는다

비밀번호·개인키·keystore 내용은 어떤 경우에도 출력하지 않는다.

사용 예:
    python scripts/verify_android_release_signing.py
    python scripts/verify_android_release_signing.py \\
        --aab build/app/outputs/bundle/productionRelease/app-production-release.aab
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY_PROPERTIES = REPO_ROOT / "android" / "key.properties"
REQUIRED_KEYS = ("storePassword", "keyPassword", "keyAlias", "storeFile")

# 디버그 keystore 비밀번호는 Android SDK 가 공개한 고정값이라 비밀이 아니다.
DEBUG_KEYSTORE = Path.home() / ".android" / "debug.keystore"
DEBUG_STORE_PASSWORD = "android"
DEBUG_ALIAS = "androiddebugkey"


def _find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / name
        for path in (candidate, candidate.with_suffix(".exe")):
            if path.is_file():
                return str(path)
    for root in (
        Path("C:/Program Files/Eclipse Adoptium"),
        Path("C:/Program Files/Java"),
        Path("/usr/lib/jvm"),
    ):
        if not root.is_dir():
            continue
        for path in root.glob(f"*/bin/{name}*"):
            if path.is_file():
                return str(path)
    return None


def _normalize_fingerprint(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


def _fingerprints(output: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in output.splitlines():
        stripped = line.strip()
        for label in ("SHA1", "SHA-1", "SHA256", "SHA-256"):
            prefix = label + ":"
            if stripped.upper().startswith(prefix):
                key = "SHA-1" if "1" in label else "SHA-256"
                found.setdefault(key, stripped[len(prefix):].strip())
    return found


def _debug_fingerprint(keytool: str) -> str | None:
    if not DEBUG_KEYSTORE.is_file():
        return None
    try:
        result = subprocess.run(
            [
                keytool, "-list", "-v",
                "-keystore", str(DEBUG_KEYSTORE),
                "-alias", DEBUG_ALIAS,
                "-storepass", DEBUG_STORE_PASSWORD,
                "-keypass", DEBUG_STORE_PASSWORD,
            ],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return None
    sha = _fingerprints(result.stdout).get("SHA-256")
    return _normalize_fingerprint(sha) if sha else None


def check_key_properties() -> tuple[bool, list[str]]:
    """key.properties 상태만 보고한다. 값은 읽되 절대 출력하지 않는다."""
    notes: list[str] = []
    if not KEY_PROPERTIES.is_file():
        notes.append("key.properties: 없음 -> release 서명 없이 빌드된다")
        return False, notes

    values: dict[str, str] = {}
    for raw in KEY_PROPERTIES.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()

    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        notes.append("key.properties: 항목 누락 -> " + ", ".join(missing))
        return False, notes

    notes.append("key.properties: 구성됨 (필수 항목 4개 모두 존재)")

    store_file = values["storeFile"]
    store_path = Path(store_file)
    if not store_path.is_absolute():
        store_path = (KEY_PROPERTIES.parent / store_file).resolve()
    if store_path.is_file():
        notes.append("keystore 파일: 존재함")
    else:
        notes.append("keystore 파일: 경로에 없음 -> 빌드가 실패한다")
        return False, notes
    return True, notes


def check_artifact(path: Path, keytool: str | None) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if not path.is_file():
        notes.append(f"산출물 없음: {path.name}")
        return False, notes

    notes.append(f"산출물: {path.name} ({path.stat().st_size:,} bytes)")

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    signature_entries = [
        name
        for name in names
        if name.startswith("META-INF/")
        and name.upper().endswith((".RSA", ".DSA", ".EC"))
    ]
    if not signature_entries:
        notes.append("서명: 없음 (UNSIGNED) - 스토어 업로드 불가")
        notes.append("      debug 키로 대체 서명되지도 않았다 (fail-closed 정상 동작)")
        return False, notes

    notes.append("서명: 있음")

    jarsigner = _find_tool("jarsigner")
    if jarsigner:
        result = subprocess.run(
            [jarsigner, "-verify", "-verbose", "-certs", str(path)],
            capture_output=True, text=True, timeout=300,
        )
        verified = "jar verified" in (result.stdout or "").lower()
        notes.append("jarsigner -verify: " + ("통과" if verified else "실패"))
        prints = _fingerprints(result.stdout or "")
        for label, value in prints.items():
            notes.append(f"인증서 {label}: {value}")
        if keytool:
            debug_sha = _debug_fingerprint(keytool)
            actual = _normalize_fingerprint(prints.get("SHA-256", ""))
            if debug_sha and actual and debug_sha == actual:
                notes.append("인증서: 디버그 인증서와 동일 - 업로드 금지")
                return False, notes
            if debug_sha and actual:
                notes.append("인증서: 디버그 인증서와 다름 (release 인증서로 보인다)")
        return verified, notes

    notes.append("jarsigner 를 찾지 못해 서명 유효성은 확인하지 못했다")
    return True, notes


def main() -> int:
    # Windows 콘솔 코드페이지가 좁아 출력에서 죽는 일이 없게 한다.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Android release 서명 상태 점검 (비밀값 미출력)"
    )
    parser.add_argument(
        "--aab",
        # applicationId 가 flavor 로 갈리면서 Play 에 올리는 산출물은
        # production variant 아래에만 생긴다.
        default="build/app/outputs/bundle/productionRelease/app-production-release.aab",
        help="검사할 AAB/APK 경로 (저장소 루트 기준)",
    )
    args = parser.parse_args()

    keytool = _find_tool("keytool")
    print("[1] 서명 설정")
    configured, notes = check_key_properties()
    for note in notes:
        print("    " + note)

    print("[2] 산출물")
    artifact = Path(args.aab)
    if not artifact.is_absolute():
        artifact = REPO_ROOT / artifact
    signed, notes = check_artifact(artifact, keytool)
    for note in notes:
        print("    " + note)

    print("[3] 참고")
    if keytool:
        debug_sha = _debug_fingerprint(keytool)
        if debug_sha:
            print("    디버그 인증서 SHA-256(공개): " + debug_sha)
    else:
        print("    keytool 을 찾지 못했다 (JDK 설치 확인)")

    print("")
    if configured and signed:
        print("RESULT: SIGNED_RELEASE_ARTIFACT_READY")
        return 0
    if not configured:
        print("RESULT: SIGNING_MATERIAL_REQUIRED")
        return 1
    print("RESULT: ARTIFACT_NOT_SIGNED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
