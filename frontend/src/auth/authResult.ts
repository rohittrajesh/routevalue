export function isSuccessfulAuthResult(value: unknown): boolean {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  if ("error" in value && value.error != null) {
    return false;
  }

  return "data" in value && value.data != null;
}
