export function isSuccessfulAuthResult(value: unknown): boolean {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  if ("error" in value && value.error != null) {
    return false;
  }

  if (!("data" in value) || value.data == null) return false;
  const data: unknown = value.data;
  if (typeof data === "object" && data !== null) {
    if ("success" in data && data.success === false) return false;
    if ("status" in data && data.status === false) return false;
  }
  return true;
}
