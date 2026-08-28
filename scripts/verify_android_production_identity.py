#!/usr/bin/env python3
"""Android production identity 검증.

Google Play 에 등록된 실제 앱은 `com.seolleyeon.app` 이다. `com.yonsei.dating`
번들을 Play 에 올리면 기존 앱의 업데이트가 아니라 **별개의 새 앱**이 되고,
기존 사용자는 업데이트를 받지 못한다. 그래서 production 산출물의 패키지는
빌드가 성공했는지와 별개로 반드시 확인해야 한다.

확인하는 것:

    1. Gradle 의 production / staging flavor applicationId
    2. google-services.json 이 두 패키지를 모두 담고 있는지
       (Google Services 플러그인은 applicationId 로 client 를 고른다)
    3. firebase_options.dart 가 flavor 별로 다른 Firebase 앱을 쓰는지
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
STAGING_PACKAGE = "com.yonsei.dating"

GRADLE = REPO_ROOT / "android" / "app" / "build.gradle.kts"
GOOGLE_SERVICES = REPO_ROOT / "android" / "app" / "google-services.json"
FIREBASE_OPTIONS = REPO_ROOT / "lib" / "firebase_options.dart"
ASSETLINKS = REPO_ROOT / "public" / "assetlinks.json"

failures: list[str] = []


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
        f"staging applicationId = {STAGING_PACKAGE}",
        flavors.get("staging") == STAGING_PACKAGE,
        str(flavors),
    )
    check(
        "두 flavor 의 패키지가 서로 다르다",
        flavors.get("production") != flavors.get("staging"),
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
    check(f"{STAGING_PACKAGE} client 포함", STAGING_PACKAGE in packages, str(packages))

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
    check("flavor 별 Android 옵션이 분리돼 있다", "androidProduction" in options)
    check(
        "production Firebase 앱 id 가 들어 있다",
        production_app_id != "" and production_app_id in options,
    )
    check("flavor 로 선택한다", "FLUTTER_APP_FLAVOR" in options)

    print("[4] assetlinks.json")
    if ASSETLINKS.is_file():
        links = json.loads(ASSETLINKS.read_text(encoding="utf-8"))
        targets = {
            entry.get("target", {}).get("package_name") for entry in links
        }
        has_production = PRODUCTION_PACKAGE in targets
        print(f"    등록된 대상 패키지: {sorted(t for t in targets if t)}")
        if not has_production:
            print(
                "    NOTE production 항목 없음 - Play 앱 서명 인증서 SHA-256 확정 후 추가해야 한다"
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
            # namespace 는 applicationId 와 별개라서 액티비티 클래스명은
            # `com.yonsei.dating.MainActivity` 로 남고, MethodChannel 이름에도
            # 같은 접두어가 쓰인다. 그것들을 실패로 보면 오탐이 된다.
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

            # staging 이 "패키지로" 선언돼 있으면 실패다.
            # 클래스명(com.yonsei.dating.MainActivity)이나 MethodChannel 이름으로
            # 등장하는 것은 정상이므로 실패로 보지 않는다.
            check(
                "staging 패키지로 선언되지 않았다",
                not declared_as_package(STAGING_PACKAGE),
                "manifest 의 package 속성이 staging 이다",
            )

    print("")
    if failures:
        print(f"RESULT: PRODUCTION_IDENTITY_FAILED ({len(failures)})")
        return 1
    print("RESULT: PRODUCTION_IDENTITY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
