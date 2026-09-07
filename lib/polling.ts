type Visibility = {
  readonly hidden: boolean;
  addEventListener(type: 'visibilitychange', listener: () => void): void;
  removeEventListener(type: 'visibilitychange', listener: () => void): void;
};
type Clock = {
  setTimeout(callback: () => void, delay: number): number;
  clearTimeout(id: number): void;
};

/** Poll only after the previous request settles. Hidden views pause by default. */
export function startPolling({run, interval, hiddenInterval, onError, visibility = document, clock = {
  setTimeout: (callback, delay) => window.setTimeout(callback, delay),
  clearTimeout: id => window.clearTimeout(id),
}}: {
  run: () => Promise<unknown>;
  interval: () => number;
  hiddenInterval?: number;
  onError?: (error: unknown) => void;
  visibility?: Visibility;
  clock?: Clock;
}) {
  let stopped = false, running = false, wakeAfterRun = false, failures = 0;
  let timer: number | undefined;
  function clear() { if (timer !== undefined) clock.clearTimeout(timer); timer = undefined; }
  function schedule(immediate = false) {
    clear();
    if (stopped || (visibility.hidden && hiddenInterval === undefined)) return;
    const base = visibility.hidden ? hiddenInterval! : interval();
    const delay = immediate ? 0 : Math.max(base, Math.min(30000, base * 2 ** Math.min(failures, 5)));
    timer = clock.setTimeout(() => void poll(), delay);
  }
  async function poll() {
    if (stopped || running || (visibility.hidden && hiddenInterval === undefined)) return;
    running = true;
    try { await run(); failures = 0; }
    catch (error) { failures++; if (!stopped) onError?.(error); }
    finally {
      running = false;
      schedule(wakeAfterRun && !visibility.hidden);
      wakeAfterRun = false;
    }
  }
  function visibilityChanged() {
    clear();
    if (running) { wakeAfterRun = !visibility.hidden; return; }
    if (visibility.hidden) schedule();
    else void poll();
  }
  visibility.addEventListener('visibilitychange', visibilityChanged);
  if (visibility.hidden) schedule(); else void poll();
  return () => { stopped = true; clear(); visibility.removeEventListener('visibilitychange', visibilityChanged); };
}
