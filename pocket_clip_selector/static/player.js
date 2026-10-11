// Pure playback helpers are also exercised by the JavaScript regression checks.
export function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const milliseconds = Math.round(seconds * 1000);
  const hours = Math.floor(milliseconds / 3600000);
  const minutes = Math.floor(milliseconds / 60000) % 60;
  const secs = Math.floor(milliseconds / 1000) % 60;
  const fraction = String(milliseconds % 1000).padStart(3, "0");
  return `${hours ? `${hours}:${String(minutes).padStart(2, "0")}` : minutes}:${String(secs).padStart(2, "0")}.${fraction}`;
}

export function clampSeek(time, duration) {
  return Math.min(duration, Math.max(0, time));
}

export function acceptedRate(video, requested) {
  try {
    video.playbackRate = requested;
  } catch {
    return { rate: video.playbackRate, accepted: false };
  }
  return { rate: video.playbackRate, accepted: Math.abs(video.playbackRate - requested) < 0.001 };
}
