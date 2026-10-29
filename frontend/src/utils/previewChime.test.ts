export {};

const originalAudio = window.AudioContext;
let chime: typeof import('./previewChime');
let audio: any;
let oscillators: any[];
beforeEach(async () => {
  jest.resetModules();
  oscillators = [];
  audio = {
    state: 'suspended', currentTime: 10, destination: {},
    resume: jest.fn(async () => { audio.state = 'running'; }),
    createOscillator: jest.fn(() => {
      const oscillator = { frequency: { setValueAtTime: jest.fn() }, connect: jest.fn(),
        start: jest.fn(), stop: jest.fn(), disconnect: jest.fn(), onended: null };
      oscillators.push(oscillator);
      return oscillator;
    }),
    createGain: jest.fn(() => ({ gain: { setValueAtTime: jest.fn(), linearRampToValueAtTime: jest.fn(),
      exponentialRampToValueAtTime: jest.fn() }, connect: jest.fn(), disconnect: jest.fn() })),
  };
  Object.defineProperty(window, 'AudioContext', { configurable: true, value: jest.fn(() => audio) });
  chime = await import('./previewChime');
});
afterEach(() => { Object.defineProperty(window, 'AudioContext', { configurable: true, value: originalAudio }); });

test('plays a short two-note chime once per completion, including distinct regenerations', async () => {
  chime.armPreviewChime();
  await chime.playPreviewReadyChime('preview:p1');
  await chime.playPreviewReadyChime('preview:p1');
  expect(audio.createOscillator).toHaveBeenCalledTimes(2);
  expect(oscillators[0].frequency.setValueAtTime).toHaveBeenCalledWith(880, 10);
  expect(oscillators[1].stop.mock.calls[0][0]).toBeLessThan(10.5);
  await chime.playPreviewReadyChime('architecture:j1');
  expect(audio.createOscillator).toHaveBeenCalledTimes(4);
});

test('does not try autoplay without a user gesture', async () => {
  await chime.playPreviewReadyChime('preview:p1');
  expect(window.AudioContext).not.toHaveBeenCalled();
});

test('audio restrictions do not reject the ready notification', async () => {
  audio.resume.mockRejectedValue(new Error('NotAllowedError'));
  chime.armPreviewChime();
  await expect(chime.playPreviewReadyChime('preview:p1')).resolves.toBeUndefined();
  expect(audio.createOscillator).not.toHaveBeenCalled();
});

test('gesture listeners are removed on unmount', () => {
  const remove = chime.installPreviewChimeUnlock();
  remove();
  document.dispatchEvent(new Event('pointerdown'));
  expect(window.AudioContext).not.toHaveBeenCalled();
  const cleanup = chime.installPreviewChimeUnlock();
  document.dispatchEvent(new Event('pointerdown'));
  expect(window.AudioContext).toHaveBeenCalledTimes(1);
  cleanup();
});
