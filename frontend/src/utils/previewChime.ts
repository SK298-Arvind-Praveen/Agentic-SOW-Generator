// A quiet, locally synthesized notification; no audio files or network requests.
let context: AudioContext | undefined;
const played = new Set<string>();

export function armPreviewChime(): void {
  try {
    const Audio = window.AudioContext || (window as any).webkitAudioContext;
    if (!Audio) return;
    if (!context || context.state === 'closed') context = new Audio();
    if (context?.state === 'suspended') void context.resume().catch(() => {});
  } catch { /* Unsupported/blocked audio must never affect generation. */ }
}

export function installPreviewChimeUnlock(): () => void {
  // Browsers require a user gesture before audio can play after a long job.
  document.addEventListener('pointerdown', armPreviewChime, true);
  document.addEventListener('keydown', armPreviewChime, true);
  return () => {
    document.removeEventListener('pointerdown', armPreviewChime, true);
    document.removeEventListener('keydown', armPreviewChime, true);
  };
}

export async function playPreviewReadyChime(completionId: string): Promise<void> {
  if (!completionId || played.has(completionId)) return;
  played.add(completionId);
  if (played.size > 100) played.delete(played.values().next().value as string);
  try {
    if (!context) return; // Do not attempt autoplay without a preceding gesture.
    if (context.state === 'suspended') await context.resume();
    if (context.state !== 'running') return;
    const start = context.currentTime;
    [880, 1174.66].forEach((frequency, index) => {
      const oscillator = context!.createOscillator();
      const gain = context!.createGain();
      const at = start + index * 0.18;
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(frequency, at);
      gain.gain.setValueAtTime(0, at);
      gain.gain.linearRampToValueAtTime(0.055, at + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.001, at + 0.23);
      oscillator.connect(gain);
      gain.connect(context!.destination);
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
      oscillator.start(at);
      oscillator.stop(at + 0.25);
    });
  } catch { /* Muted tabs/autoplay restrictions are non-fatal. */ }
}
