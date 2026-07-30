import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scans_root_festival_and_built_client_surfaces(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    festival = tmp_path / "festival_web"
    _write(root / "lib" / "features" / "profile" / "safe.dart", "const ok = 'avatar';\n")
    _write(
        festival / "src" / "leaky.ts",
        "window.localStorage.setItem('photoUrl', 'gs://seolleyeon-private-source-photos/users/u/source/p.jpg');\n",
    )
    _write(
        root / "build" / "web" / "main.dart.js",
        "const rawFaceLandmarks = [[0.1, 0.2]];\n",
    )
    _write(
        root / "functions" / "src" / "safe.ts",
        "const redactionRegex = /X-Goog-Signature=[^&]+/;\n",
    )
    _write(
        root / "docs" / "safe.md",
        "Example redaction regex for seolleyeon-private-source-photos and X-Goog-Signature.\n",
    )

    summary = scan_client_surfaces(root, festival_roots=[festival])

    assert summary.scanned_file_count == 3
    assert summary.leakage_count == 2


def test_built_client_allows_policy_patterns_but_rejects_arbitrary_private_buckets(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    safe_root = tmp_path / "safe_root"
    _write(
        safe_root / "build" / "web" / "main.dart.js",
        "const policy = 'seolleyeon(?:-final|-festival)?-(?:private-source-photos|avatar-temp|chat-profile-photos)';\n",
    )
    assert scan_client_surfaces(safe_root).client_code_leakage_count == 0

    leaky_root = tmp_path / "leaky_root"
    leaked_urls = [
        "gs://qa-tenant-17-private-source-photos/users/u/source/p.jpg",
        "https://storage.googleapis.com/tenant.alpha-avatar-temp/users/u/candidate/p.png",
        "https://tenant99-chat-profile-photos.storage.googleapis.com/users/u/chat-profile/p.jpg",
    ]
    for index, leaked_url in enumerate(leaked_urls):
        _write(
            leaky_root / "build" / "web" / f"chunk-{index}.js",
            f"const leaked = '{leaked_url}';\n",
        )
    assert scan_client_surfaces(leaky_root).client_code_leakage_count == 3

def test_festival_private_media_markers_are_detected(tmp_path):
    from scripts.privacy_client_scanner import value_contains_privacy_leak
    from scripts.qa_media_privacy import run_fixture_checks

    festival_urls = [
        "https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/p.jpg",
        "https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png",
        "https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat-profile/p.jpg",
    ]
    assert all(value_contains_privacy_leak(value) for value in festival_urls)

    root = tmp_path / "root"
    festival = tmp_path / "festival_web"
    _write(root / "lib" / "features" / "safe.dart", "const safe = true;\n")
    for index, value in enumerate(festival_urls):
        _write(festival / "src" / f"leak_{index}.ts", f"const leaked = '{value}';\n")

    summary = run_fixture_checks(
        {
            "users": {},
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {},
        },
        repo_root=root,
        festival_roots=[festival],
    )

    assert summary.scanned_file_count == 4
    assert summary.client_code_leakage_count == 3
    assert summary.passed is False

def test_fixture_checks_browser_storage_public_reports_and_logs():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {},
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {},
            "browserStorage": {
                "localStorage": {
                    "lastPhotoUrl": "https://cdn.example/avatar.png?X-Goog-Signature=private-token",
                }
            },
            "reports": {
                "r1": {
                    "reportedPhotoUrl": "gs://seolleyeon-private-source-photos/users/u/source/p.jpg",
                }
            },
            "logs": {
                "l1": {
                    "message": "persisted faceLandmarks in public audit log",
                }
            },
        },
        check_client_code=False,
    )

    assert summary.browser_storage_leakage_count == 1
    assert summary.public_report_leakage_count == 1
    assert summary.public_log_leakage_count == 1
    assert summary.passed is False


def test_cli_outputs_sanitized_counts_only(tmp_path):
    fixture = {
        "users": {
            "uid-secret-123": {
                "avatar": {
                    "approvedAvatarUrl": (
                        "https://cdn.example/avatar.png?X-Goog-Signature=secret-token-abc"
                    )
                }
            }
        },
        "userPrivateMedia": {},
        "clipEmbeddings": {},
        "modelRecs": {},
    }
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "qa_media_privacy.py"),
            "--fixture",
            str(fixture_path),
            "--no_client_code_check",
            "--fail_on_warning",
            "--dry_run",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    output = completed.stdout + completed.stderr
    assert '"public_leakage_count": 1' in output
    assert "uid-secret-123" not in output
    assert "secret-token-abc" not in output
    assert "X-Goog-Signature" not in output


def test_client_debug_print_raw_privacy_values_fail(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    _write(
        root / "lib" / "features" / "privacy" / "unsafe_logs.dart",
        """
void logRaw({
  required String uid,
  required String email,
  required String token,
  required String sourcePhotoUrl,
  required String authorIdStr,
  required String currentUserId,
  required Object e,
  required StackTrace st,
}) {
  debugPrint('uid=$uid email=$email token=$token source=$sourcePhotoUrl error=$e stack=$st');
  debugPrint('author=$authorIdStr current=$currentUserId');
  // print('comment example $token $error');
  print('[API Request] ${request['url']}');
  print('[API Error] $error');
}
""",
    )

    summary = scan_client_surfaces(root, festival_roots=[])

    assert summary.scanned_file_count == 1
    assert summary.leakage_count == 1


def test_client_debug_print_safe_privacy_wrappers_and_status_pass(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    _write(
        root / "lib" / "features" / "privacy" / "safe_logs.dart",
        """
void logSafe({
  required String uid,
  required String token,
  required Object e,
  required dynamic storagePath,
}) {
  debugPrint('token/email labels only');
  debugPrint('uid=${PrivacyLogUtils.idFingerprint(uid)}');
  debugPrint('path=${PrivacyLogUtils.pathFingerprint(storagePath)}');
  debugPrint('error=${PrivacyLogUtils.errorSummary(e)} code=${e.code} type=${e.runtimeType}');
  debugPrint('hasToken=${token != null && token.isNotEmpty}');
  print('constant token/email labels only');
  print('hasToken=${token != null && token.isNotEmpty} error=${PrivacyLogUtils.errorSummary(e)}');
}
""",
    )

    summary = scan_client_surfaces(root, festival_roots=[])

    assert summary.scanned_file_count == 1
    assert summary.leakage_count == 0


def test_client_debug_print_safe_metadata_and_optional_presence_pass(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    _write(
        root / "lib" / "features" / "privacy" / "safe_metadata_logs.dart",
        """
void logMetadata({
  required Uri uri,
  required dynamic request,
  required dynamic response,
  required dynamic e,
  required Map<String, dynamic> userInfo,
}) {
  debugPrint('uri scheme=${uri.scheme} host=${uri.host} queryKeys=${uri.queryParameters.keys.join(',')}');
  debugPrint('http method=${request.method} status=${response.statusCode} url=${PrivacyLogUtils.pathFingerprint(uri.toString())}');
  debugPrint('hasErrorMessage=${e.message?.isNotEmpty ?? false}');
  debugPrint('hasNickname=${userInfo['nickname']?.toString().isNotEmpty ?? false}');
  // debugPrint('commented raw token=$token uid=$uid error=$error');
  /* print('example url=$url path=$path stack=$stackTrace'); */
}
""",
    )

    summary = scan_client_surfaces(root, festival_roots=[])

    assert summary.scanned_file_count == 1
    assert summary.leakage_count == 0


def test_client_debug_print_safe_festival_central_wrappers_pass(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    festival = tmp_path / "festival_web"
    _write(
        festival / "src" / "safe_festival_logs.dart",
        """
void logFestival({
  required dynamic error,
  required dynamic user,
  required String token,
}) {
  debugPrint('user=${PrivacyLogUtils.idFingerprint(user.uid)} token=${PrivacyLogUtils.idFingerprint(token)}');
}
""",
    )
    _write(root / "lib" / "features" / "privacy" / "safe.dart", "const ok = true;\n")

    summary = scan_client_surfaces(root, festival_roots=[festival])

    assert summary.scanned_file_count == 2
    assert summary.leakage_count == 0


def test_client_debug_print_local_wrapper_names_are_not_trusted(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    _write(
        root / "lib" / "features" / "privacy" / "unsafe_local_wrappers.dart",
        """
void logUnsafe(dynamic error, String uid, String path) {
  debugPrint('error=${_safeErrorType(error)}');
  debugPrint('uid=${_safeHashPrefix(uid)}');
  debugPrint('uid=${_logHashPrefix(uid)}');
  debugPrint('path=${_redactStoragePath(path)}');
}
""",
    )

    summary = scan_client_surfaces(root, festival_roots=[])

    assert summary.scanned_file_count == 1
    assert summary.leakage_count == 1

def test_client_debug_print_unsafe_direct_raw_values_fail(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    _write(
        root / "lib" / "features" / "privacy" / "unsafe_direct_logs.dart",
        """
void logUnsafe({
  required dynamic error,
  required StackTrace stack,
  required Map<String, dynamic> request,
}) {
  print(error);
  debugPrint(stack.toString());
  print(request['url']);
}
""",
    )

    summary = scan_client_surfaces(root, festival_roots=[])

    assert summary.scanned_file_count == 1
    assert summary.leakage_count == 1


def test_client_debug_print_unsafe_interpolated_raw_values_fail(tmp_path):
    from scripts.qa_media_privacy import scan_client_surfaces

    root = tmp_path / "root"
    _write(
        root / "lib" / "features" / "privacy" / "unsafe_interpolated_logs.dart",
        """
void logUnsafe({
  required String uid,
  required String email,
  required String token,
  required String url,
  required String path,
  required dynamic error,
  required Map<String, dynamic> userInfo,
}) {
  debugPrint('uid=$uid email=$email token=$token url=$url path=$path error=$error');
  debugPrint('nickname=${userInfo['nickname'] != null ? userInfo['nickname'] : 'none'}');
}
""",
    )

    summary = scan_client_surfaces(root, festival_roots=[])

    assert summary.scanned_file_count == 1
    assert summary.leakage_count == 1