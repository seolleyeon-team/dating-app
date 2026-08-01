const PRIVATE_MEDIA_BUCKET_MARKER =
  /(?:private-source-photos|avatar-temp|chat-profile-photos)/i;

function safeDecodeUriComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function isSafePublicAvatarUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  if (!trimmed) return false;

  const decodedLower = safeDecodeUriComponent(trimmed).toLowerCase();
  if (
    decodedLower.startsWith("gs://") ||
    decodedLower.startsWith("gcs://") ||
    PRIVATE_MEDIA_BUCKET_MARKER.test(decodedLower) ||
    decodedLower.includes("x-goog-") ||
    decodedLower.includes("x-amz-") ||
    decodedLower.includes("googleaccessid") ||
    decodedLower.includes("signature=") ||
    decodedLower.includes("expires=") ||
    decodedLower.includes("awsaccesskeyid") ||
    decodedLower.includes("signedurl") ||
    /\/source\//.test(decodedLower) ||
    /\/jobs\//.test(decodedLower) ||
    /\/candidates\//.test(decodedLower)
  ) {
    return false;
  }

  try {
    const parsed = new URL(trimmed);
    if (
      (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
      !parsed.hostname
    ) {
      return false;
    }
    const host = parsed.hostname.toLowerCase();
    const path = safeDecodeUriComponent(parsed.pathname).toLowerCase();
    const bucketFromVirtualHost = host.endsWith(".storage.googleapis.com")
      ? host.replace(".storage.googleapis.com", "")
      : "";
    if (
      PRIVATE_MEDIA_BUCKET_MARKER.test(bucketFromVirtualHost) ||
      /\/source\//.test(path) ||
      /\/jobs\//.test(path) ||
      /\/candidates\//.test(path)
    ) {
      return false;
    }
  } catch {
    return false;
  }

  return true;
}
