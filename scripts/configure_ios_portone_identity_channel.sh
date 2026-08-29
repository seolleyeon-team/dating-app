#!/bin/zsh
# Configure the local, ignored Xcode setting used by Debug/Profile/Release.
# The Channel Key is a client-side identifier, but keeping it out of Git makes
# it possible to use a different PortOne channel per developer or environment.

set -euo pipefail

project_root="${0:A:h:h}"
local_xcconfig="$project_root/ios/Flutter/Local.xcconfig"

read -r -s "PORTONE_CHANNEL_KEY?PortOne 실 통합인증 Channel Key를 입력하세요: "
print

if [[ -z "$PORTONE_CHANNEL_KEY" ]]; then
  print -u2 "Channel Key가 비어 있습니다. 변경하지 않았습니다."
  exit 1
fi

if [[ "$PORTONE_CHANNEL_KEY" != channel-key-* ]]; then
  print -u2 "Channel Key 형식이 올바르지 않습니다. 'channel-key-'로 시작하는 값을 입력하세요."
  exit 1
fi

encoded_define=$(printf %s "PORTONE_KG_INICIS_IDENTITY_CHANNEL_KEY=$PORTONE_CHANNEL_KEY" | base64 | tr -d '\n')
temp_xcconfig=$(mktemp)

if [[ -f "$local_xcconfig" ]]; then
  # Retain unrelated developer-local settings while replacing only this value.
  sed '/^DART_DEFINES[[:space:]]*=/d' "$local_xcconfig" > "$temp_xcconfig"
fi

cat >> "$temp_xcconfig" <<EOF

// Generated locally by scripts/configure_ios_portone_identity_channel.sh.
// This file is gitignored and applies to Xcode Debug, Profile, and Archive.
DART_DEFINES = $encoded_define
EOF

mv "$temp_xcconfig" "$local_xcconfig"
print "iOS Xcode용 포트원 실 통합인증 Channel Key를 저장했습니다."
