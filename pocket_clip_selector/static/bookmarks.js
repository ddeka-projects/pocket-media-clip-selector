// Quick Log accepts compact digits or pasted colon times, never decimal numbers.
export const MAX_SECONDS = 3599999.999;
export function parseTimestamp(raw) {
  const value = String(raw).trim();
  if (!value || value.length > 16) throw new Error("Enter a time, such as 1742 for 17:42.");
  let hours = 0, minutes = 0, seconds = 0;
  if (/^[0-9]+$/.test(value)) {
    seconds = Number(value.slice(-2));
    minutes = Number(value.slice(-4, -2) || 0);
    hours = Number(value.slice(0, -4) || 0);
  } else if (/^[0-9]+:[0-9]{1,2}(?::[0-9]{1,2})?$/.test(value)) {
    const parts = value.split(":").map(Number);
    seconds = parts.pop(); minutes = parts.pop(); hours = parts.pop() || 0;
    if (value.split(":").length === 3 && minutes >= 60) throw new Error("Minutes must be 00–59 in an hours:minutes:seconds time.");
  } else throw new Error("Use digits like 1742, or a time like 17:42 or 1:14:32.");
  if (seconds >= 60) throw new Error("Seconds must be 00–59; the entered time was not changed.");
  if (/^[0-9]+$/.test(value) && value.length >= 5 && minutes >= 60) throw new Error("Minutes must be 00–59 when you include hours.");
  const total = hours * 3600 + minutes * 60 + seconds;
  if (!Number.isSafeInteger(total) || total < 0 || total > MAX_SECONDS) throw new Error("Use a time no later than 999:59:59.");
  return total;
}

export function formatBookmark(time) {
  if (!Number.isFinite(time) || time < 0) return "—";
  const total = Math.floor(time), hours = Math.floor(total / 3600), minutes = Math.floor(total / 60) % 60;
  return `${hours ? `${hours}:${String(minutes).padStart(2, "0")}` : minutes}:${String(total % 60).padStart(2, "0")}`;
}

export function compactTimestamp(time) {
  return formatBookmark(time).replaceAll(":", "");
}
