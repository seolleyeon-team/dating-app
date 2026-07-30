#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/p1_chat_real_photo_common.sh
source "$SCRIPT_DIR/p1_chat_real_photo_common.sh" "$@"

require_command git
require_command rg

info "Checking rules protections and local diff."
rg -n "userPrivateMedia|clipEmbeddings|chatRoomDoesNotPersistPrivateMedia|chatRealPhotoUrl|realProfilePhotoUrl|sourcePhotoUrl|signedUrl|seolleyeon-chat-profile-photos" firestore.rules storage.rules
rg -n "allow read, write: if false|isApprovedAvatarBucket|isChatProfilePhotoBucket" storage.rules

git diff -- firestore.rules storage.rules
