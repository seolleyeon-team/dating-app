#!/usr/bin/env python3
"""Android production identity 검증.

Google Play 에 등록된 실제 앱은 `com.seolleyeon.app` 이다. production과
staging flavor 모두 이 운영 패키지를 사용하며, 별도의 staging 패키지는
사용하지 않는다. 그래서 산출물의 패키지는 빌드가 성공했는지와 별개로
반드시 확인해야 한다.

확인하는 것:

    1. Gradle 의 production / staging flavor applicationId가 운영 패키지인지
    2. google-services.json 이 운영 패키지만 담고 있는지
       (Google Services 플러그인은 applicationId 로 client 를 고른다)
    3. firebase_options.dart 가 운영 Firebase 앱을 쓰는지
    4. assetlinks.json 의 대상 패키지
    5. (AAB 를 주면) 산출물의 실제 applicationId

사용 예:
    python scripts/verify_android_production_identity.py
    python scripts/verify_android_production_identity.py \\
        --aab build/app/outputs/bundle/productionRelease/app-production-release.aab
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PACKAGE = "com.seolleyeon.app"

GRADLE = REPO_ROOT / "android" / "app" / "build.gradle.kts"
GOOGLE_SERVICES = REPO_ROOT / "android" / "app" / "google-services.json"
FIREBASE_OPTIONS = REPO_ROOT / "lib" / "firebase_options.dart"
ASSETLINKS = REPO_ROOT / "public" / "assetlinks.json"

# Google Play Console -> 설정 -> 앱 무결성 에서 확인한 공개 지문.
#
# 앱 서명 인증서: Play 가 사용자에게 배포하는 APK 를 서명하는 키.
#   설치된 앱이 갖는 인증서이므로 App Links / Kakao key hash 는 이 값을 쓴다.
# 업로드 인증서: 우리가 AAB 에 서명해 Play 에 올릴 때 쓰는 키.
#   Play 가 검증하고 벗겨내므로 설치본에는 남지 않는다.
PLAY_APP_SIGNING_SHA256 = (
    "ec75e01b4744773122cffc22b3a46facd31e0e7cee513ce08a9cc42c503651cf"
)
PLAY_UPLOAD_SHA256 = (
    "02035e72cde18bb20acb472c225c1288d05b0348caf3a5179f6a9872cb44a9c6"
)

failures: list[str] = []


def _normalize(fingerprint: str) -> str:
    return re.sub(r"[^0-9a-f]", "", fingerprint.lower())


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"    ok   {name}")
    else:
        failures.append(name)
        print(f"    FAIL {name}" + (f" -> {detail}" if detail else ""))


def flavor_application_ids(source: str) -> dict[str, str]:
    """productFlavors 블록에서 flavor -> applicationId 를 읽는다."""
    result: dict[str, str] = {}
    for match in re.finditer(
        r'create\("(\w+)"\)\s*\{(.*?)\n        \}', source, re.DOTALL
    ):
        flavor, body = match.group(1), match.group(2)
        app_id = re.search(r'applicationId\s*=\s*"([^"]+)"', body)
        if app_id:
            result[flavor] = app_id.group(1)
    return result


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Android production identity 검증")
    parser.add_argument("--aab", default=None, help="검사할 production AAB 경로")
    args = parser.parse_args()

    print("[1] Gradle flavor")
    gradle = GRADLE.read_text(encoding="utf-8")
    flavors = flavor_application_ids(gradle)
    check(
        f"production applicationId = {PRODUCTION_PACKAGE}",
        flavors.get("production") == PRODUCTION_PACKAGE,
        str(flavors),
    )
    check(
        f"staging applicationId = {PRODUCTION_PACKAGE}",
        flavors.get("staging") == PRODUCTION_PACKAGE,
        str(flavors),
    )
    check(
        "production/staging flavor가 같은 운영 패키지를 쓴다",
        flavors.get("production") == flavors.get("staging") == PRODUCTION_PACKAGE,
    )
    # defaultConfig 에 applicationId 가 남아 있으면 flavor 를 빼먹은 빌드가
    # 조용히 그 값으로 나간다.
    default_block = re.search(r"defaultConfig\s*\{(.*?)\n    \}", gradle, re.DOTALL)
    check(
        "defaultConfig 에 applicationId 기본값이 없다",
        default_block is not None
        and "applicationId" not in re.sub(r"//[^\n]*", "", default_block.group(1)),
    )

    print("[2] google-services.json")
    config = json.loads(GOOGLE_SERVICES.read_text(encoding="utf-8"))
    packages = {
        client["client_info"]["android_client_info"]["package_name"]
        for client in config.get("client", [])
    }
    check(f"{PRODUCTION_PACKAGE} client 포함", PRODUCTION_PACKAGE in packages, str(packages))
    check(
        "운영 패키지 외 client가 없다",
        packages == {PRODUCTION_PACKAGE},
        str(packages),
    )

    print("[3] firebase_options.dart")
    options = FIREBASE_OPTIONS.read_text(encoding="utf-8")
    production_app_id = next(
        (
            client["client_info"]["mobilesdk_app_id"]
            for client in config["client"]
            if client["client_info"]["android_client_info"]["package_name"]
            == PRODUCTION_PACKAGE
        ),
        "",
    )
    check("운영 Android 옵션이 있다", "androidProduction" in options)
    check(
        "production Firebase 앱 id 가 들어 있다",
        production_app_id != "" and production_app_id in options,
    )
    check("제거된 별도 Android 앱 옵션이 없다", "androidStaging" not in options)

    print("[4] assetlinks.json")
    if ASSETLINKS.is_file():
        links = json.loads(ASSETLINKS.read_text(encoding="utf-8"))
        entries = {
            entry.get("target", {}).get("package_name"): entry.get("target", {})
            for entry in links
        }
        print(f"    등록된 대상 패키지: {sorted(t for t in entries if t)}")
        check(f"{PRODUCTION_PACKAGE} 항목 존재", PRODUCTION_PACKAGE in entries)

        production_entry = entries.get(PRODUCTION_PACKAGE, {})
        fingerprints = {
            _normalize(value)
            for value in production_entry.get("sha256_cert_fingerprints", [])
        }
        # Play 가 재서명하므로 사용자 기기에 설치된 앱은 앱 서명 인증서를 갖는다.
        # 업로드 인증서를 적으면 링크 검증이 실패한다.
        check(
            "production 지문 = Play 앱 서명 인증서",
            PLAY_APP_SIGNING_SHA256 in fingerprints,
            "앱 서명 인증서가 아니다",
        )
        check(
            "업로드 인증서를 쓰지 않았다",
            PLAY_UPLOAD_SHA256 not in fingerprints,
            "업로드 인증서로는 설치본 링크가 검증되지 않는다",
        )
    else:
        print("    assetlinks.json 없음")

    if args.aab:
        print("[5] AAB 산출물")
        path = Path(args.aab)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            check("AAB 존재", False, str(path.name))
        else:
            with zipfile.ZipFile(path) as archive:
                manifest = archive.read("base/manifest/AndroidManifest.xml")
            blob = manifest.decode("utf-8", errors="ignore")

            # manifest 의 `package` 속성 값만 본다.
            #
            # 패키지 문자열이 산출물 어딘가에 등장하는 것 자체는 정상이다.
            # namespace는 applicationId와 별개일 수 있으므로, 패키지 문자열이
            # 산출물 어딘가에 등장하는 것 자체가 manifest 오류를 뜻하지 않는다.
            def declared_as_package(token: str) -> bool:
                """`package` 속성 값으로 선언됐는지.

                protobuf 라 속성 이름과 값 사이에 길이 바이트 몇 개가 낀다.
                그래서 바로 앞 몇 바이트 안에 `package` 가 있는지로 판단한다.
                """
                for match in re.finditer(re.escape(token), blob):
                    window = blob[max(0, match.start() - 12):match.start()]
                    if "package" in window:
                        return True
                return False

            check(
                f"AAB manifest package = {PRODUCTION_PACKAGE}",
                declared_as_package(PRODUCTION_PACKAGE),
                "package 속성에서 production 패키지를 찾지 못했다",
            )


    print("")
    if failures:
        print(f"RESULT: PRODUCTION_IDENTITY_FAILED ({len(failures)})")
        return 1
    print("RESULT: PRODUCTION_IDENTITY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
