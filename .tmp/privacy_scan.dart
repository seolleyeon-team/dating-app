import 'dart:io';

void main() {
  final findings = <String>[];
  for (final file in Directory('../lib').listSync(recursive: true)) {
    if (file is! File || !file.path.endsWith('.dart')) continue;
    final source = file.readAsStringSync();
    for (final finding in _unsafeLogFindings(source)) {
      findings.add('${file.path}: ${finding.trim()}');
    }
  }
  if (findings.isNotEmpty) {
    stderr.writeln(findings.join('\n'));
    exitCode = 1;
  } else {
    stdout.writeln('privacy log scanner: 0 findings');
  }
}
final _safePrivacyLogWrapper = RegExp(
  r'\b(?:PrivacyLogUtils\.\w+|FirebaseDiagnostics\.safeErrorForLog|_logHashPrefix|_safeHashPrefix|_safeErrorType|_?redact\w*|redact\w*)\s*\(',
  caseSensitive: false,
);
final _allowedErrorMember = RegExp(
  r'^\s*[A-Za-z_][A-Za-z0-9_]*\s*\.\s*(?:code|runtimeType)\s*$',
);
final _allowedMetadata = RegExp(
  r'^\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*\.\s*(?:scheme|host|method|status|statusCode)|[A-Za-z_][A-Za-z0-9_]*(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*)*\s*\.\s*query(?:Parameters)?\s*\.\s*keys(?:\s*\.\s*(?:toList|join|length)\s*\([^)]*\))?|queryKeys(?:\s*\.\s*(?:toList|join|length)\s*\([^)]*\))?)\s*$',
  caseSensitive: false,
);
final _rawError = RegExp(
  r'(?:^|[^A-Za-z0-9_.$])(?:e|st|error|exception|stack|stackTrace)(?:\s*\.\s*(?:toString|message)\s*\(\s*\)|\s*\.\s*message)?(?:$|[^A-Za-z0-9_])',
  caseSensitive: false,
);
final _rawIdentity = RegExp(
  r'(?:^|[^A-Za-z0-9_])(?:uid|userId|kakaoUserId|firebaseUid|email|nickname|phone)(?:$|[^A-Za-z0-9_])',
  caseSensitive: false,
);
final _rawResource = RegExp(
  r'(?:^|[^A-Za-z0-9_])(?:token|url|uri|storage(?:Path|Url|Ref)?|path|gcs(?:Uri|Url|Path)?|source(?:Photo)?(?:Url|Uri|Path|Ref)?)(?:$|[^A-Za-z0-9_])',
  caseSensitive: false,
);
final _mapSensitiveKey = RegExp(
  r'''\[\s*['"](?:uid|userId|kakaoUserId|firebaseUid|email|nickname|phone|token|url|uri|storagePath|storageUrl|path|gcsUri|source|sourceUrl|sourcePhotoUrl)['"]\s*\]''',
  caseSensitive: false,
);
final _booleanStatus = RegExp(
  r'(?:[!=]=\s*null|\.is(?:Not)?Empty\b|\b(?:is|has|can|should)[A-Z_A-Za-z0-9]*\b|&&|\|\|)',
);
final _topLevelStringArgument = RegExp(
  r'''^\s*(?:r)?(?:'''
  "'''"
  r'''|"""|'|")''',
);

List<String> _unsafeLogFindings(String text) {
  return _findLogCallArgs(
    text,
  ).where(_logCallHasUnsafePrivacyValue).toList(growable: false);
}

List<String> _findLogCallArgs(String text) {
  final calls = <String>[];
  var index = 0;
  var state = _ScanState.code;
  var quote = '';
  var triple = false;

  while (index < text.length) {
    final char = text[index];
    final next = index + 1 < text.length ? text[index + 1] : '';
    if (state == _ScanState.lineComment) {
      if (char == '\n') state = _ScanState.code;
      index++;
      continue;
    }
    if (state == _ScanState.blockComment) {
      if (char == '*' && next == '/') {
        state = _ScanState.code;
        index += 2;
      } else {
        index++;
      }
      continue;
    }
    if (state == _ScanState.string) {
      if (char == '\\\\') {
        index += 2;
        continue;
      }
      if (triple && text.startsWith(quote * 3, index)) {
        state = _ScanState.code;
        index += 3;
        continue;
      }
      if (!triple && char == quote) state = _ScanState.code;
      index++;
      continue;
    }
    if (char == '/' && next == '/') {
      state = _ScanState.lineComment;
      index += 2;
      continue;
    }
    if (char == '/' && next == '*') {
      state = _ScanState.blockComment;
      index += 2;
      continue;
    }
    if (char == "'" || char == '"') {
      quote = char;
      triple = text.startsWith(char * 3, index);
      state = _ScanState.string;
      index += triple ? 3 : 1;
      continue;
    }

    final name = _logCallNameAt(text, index);
    if (name == null) {
      index++;
      continue;
    }
    var cursor = index + name.length;
    while (cursor < text.length && text[cursor].trim().isEmpty) {
      cursor++;
    }
    if (cursor >= text.length || text[cursor] != '(') {
      index++;
      continue;
    }
    final read = _readParenthesizedArgument(text, cursor);
    if (read == null) {
      index += name.length;
      continue;
    }
    calls.add(read.value);
    index = read.end;
  }

  return calls;
}

String? _logCallNameAt(String text, int index) {
  for (final name in const ['debugPrint', 'print']) {
    final end = index + name.length;
    if (!text.startsWith(name, index)) continue;
    final beforeOk = index == 0 || !_isIdentifierOrMember(text[index - 1]);
    final afterOk = end == text.length || !_isIdentifier(text[end]);
    if (beforeOk && afterOk) return name;
  }
  return null;
}

_ReadResult? _readParenthesizedArgument(String text, int openIndex) {
  var depth = 0;
  var index = openIndex;
  var state = _ScanState.code;
  var quote = '';
  var triple = false;
  final start = openIndex + 1;

  while (index < text.length) {
    final char = text[index];
    final next = index + 1 < text.length ? text[index + 1] : '';
    if (state == _ScanState.lineComment) {
      if (char == '\n') state = _ScanState.code;
      index++;
      continue;
    }
    if (state == _ScanState.blockComment) {
      if (char == '*' && next == '/') {
        state = _ScanState.code;
        index += 2;
      } else {
        index++;
      }
      continue;
    }
    if (state == _ScanState.string) {
      if (char == '\\\\') {
        index += 2;
        continue;
      }
      if (triple && text.startsWith(quote * 3, index)) {
        state = _ScanState.code;
        index += 3;
        continue;
      }
      if (!triple && char == quote) state = _ScanState.code;
      index++;
      continue;
    }
    if (char == '/' && next == '/') {
      state = _ScanState.lineComment;
      index += 2;
      continue;
    }
    if (char == '/' && next == '*') {
      state = _ScanState.blockComment;
      index += 2;
      continue;
    }
    if (char == "'" || char == '"') {
      quote = char;
      triple = text.startsWith(char * 3, index);
      state = _ScanState.string;
      index += triple ? 3 : 1;
      continue;
    }
    if (char == '(') {
      depth++;
    } else if (char == ')') {
      depth--;
      if (depth == 0) {
        return _ReadResult(text.substring(start, index), index + 1);
      }
    }
    index++;
  }
  return null;
}

List<String> _stringInterpolations(String argument) {
  final interpolations = <String>[];
  var index = 0;
  var state = _ScanState.code;
  var quote = '';
  var triple = false;

  while (index < argument.length) {
    final char = argument[index];
    if (state == _ScanState.code) {
      if (char == "'" || char == '"') {
        quote = char;
        triple = argument.startsWith(char * 3, index);
        state = _ScanState.string;
        index += triple ? 3 : 1;
        continue;
      }
      index++;
      continue;
    }
    if (char == '\\\\') {
      index += 2;
      continue;
    }
    if (triple && argument.startsWith(quote * 3, index)) {
      state = _ScanState.code;
      index += 3;
      continue;
    }
    if (!triple && char == quote) {
      state = _ScanState.code;
      index++;
      continue;
    }
    if (char == r'$') {
      if (index + 1 < argument.length && argument[index + 1] == '{') {
        final read = _readBracedInterpolation(argument, index + 1);
        if (read != null) {
          interpolations.add(read.value);
          index = read.end;
          continue;
        }
      }
      final match = RegExp(
        r'\$([A-Za-z_][A-Za-z0-9_]*(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*)*)',
      ).matchAsPrefix(argument.substring(index));
      if (match != null) {
        interpolations.add(match.group(1)!);
        index += match.group(0)!.length;
        continue;
      }
    }
    index++;
  }
  return interpolations;
}

_ReadResult? _readBracedInterpolation(String text, int openIndex) {
  var depth = 0;
  var index = openIndex;
  final start = openIndex + 1;
  while (index < text.length) {
    final char = text[index];
    if (char == '{') {
      depth++;
    } else if (char == '}') {
      depth--;
      if (depth == 0) {
        return _ReadResult(text.substring(start, index), index + 1);
      }
    }
    index++;
  }
  return null;
}

bool _logCallHasUnsafePrivacyValue(String argument) {
  for (final expression in _stringInterpolations(argument)) {
    if (_expressionHasUnsafePrivacyLogValue(expression)) return true;
  }
  if (_topLevelStringArgument.hasMatch(argument)) return false;
  return _expressionHasUnsafePrivacyLogValue(_withoutStringLiterals(argument));
}

bool _expressionHasUnsafePrivacyLogValue(String expression) {
  if (_expressionIsSafePrivacyLogValue(expression)) return false;
  final expr = expression.trim();
  return _mapSensitiveKey.hasMatch(expr) ||
      _rawError.hasMatch(expr) ||
      _rawIdentity.hasMatch(expr) ||
      _rawResource.hasMatch(expr);
}

bool _expressionIsSafePrivacyLogValue(String expression) {
  final expr = expression.trim();
  if (expr.isEmpty) return true;
  if (_allowedErrorMember.hasMatch(expr)) return true;
  if (_allowedMetadata.hasMatch(expr)) return true;
  if (_safePrivacyLogWrapper.hasMatch(expr)) return true;
  return _expressionIsBooleanStatus(expr);
}

bool _expressionIsBooleanStatus(String expression) {
  return _booleanStatus.hasMatch(expression) &&
      !expression.contains('.toString(') &&
      !_hasTernaryOperator(expression);
}

bool _hasTernaryOperator(String expression) {
  var index = 0;
  var state = _ScanState.code;
  var quote = '';
  var triple = false;
  while (index < expression.length) {
    final char = expression[index];
    final next = index + 1 < expression.length ? expression[index + 1] : '';
    if (state == _ScanState.string) {
      if (char == '\\\\') {
        index += 2;
        continue;
      }
      if (triple && expression.startsWith(quote * 3, index)) {
        state = _ScanState.code;
        index += 3;
        continue;
      }
      if (!triple && char == quote) state = _ScanState.code;
      index++;
      continue;
    }
    if (char == "'" || char == '"') {
      quote = char;
      triple = expression.startsWith(char * 3, index);
      state = _ScanState.string;
      index += triple ? 3 : 1;
      continue;
    }
    if (char == '?' && next != '.' && next != '?') return true;
    index++;
  }
  return false;
}

String _withoutStringLiterals(String argument) {
  final result = StringBuffer();
  var index = 0;
  var state = _ScanState.code;
  var quote = '';
  var triple = false;
  while (index < argument.length) {
    final char = argument[index];
    if (state == _ScanState.code) {
      if (char == "'" || char == '"') {
        quote = char;
        triple = argument.startsWith(char * 3, index);
        state = _ScanState.string;
        index += triple ? 3 : 1;
        result.write(' ');
        continue;
      }
      result.write(char);
      index++;
      continue;
    }
    if (char == '\\\\') {
      index += 2;
      continue;
    }
    if (triple && argument.startsWith(quote * 3, index)) {
      state = _ScanState.code;
      index += 3;
      result.write(' ');
      continue;
    }
    if (!triple && char == quote) {
      state = _ScanState.code;
      index++;
      result.write(' ');
      continue;
    }
    index++;
  }
  return result.toString();
}

bool _isIdentifier(String char) => RegExp(r'[A-Za-z0-9_]').hasMatch(char);
bool _isIdentifierOrMember(String char) =>
    RegExp(r'[A-Za-z0-9_.]').hasMatch(char);

enum _ScanState { code, string, lineComment, blockComment }

class _ReadResult {
  const _ReadResult(this.value, this.end);

  final String value;
  final int end;
}
