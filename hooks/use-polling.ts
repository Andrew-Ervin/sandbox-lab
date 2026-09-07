'use client';
import {useEffect, useRef} from 'react';
import {startPolling} from '@/lib/polling';

export function usePolling(run: () => Promise<unknown>, interval: number | (() => number), {
  enabled = true, hiddenInterval, onError,
}: {enabled?: boolean; hiddenInterval?: number; onError?: (error: unknown) => void} = {}) {
  const latest = useRef({run, interval, onError});
  const pending = useRef<Promise<unknown> | null>(null);
  latest.current = {run, interval, onError};
  useEffect(() => {
    if (!enabled) return;
    return startPolling({
      run: () => {
        // Rapidly leaving/reopening a view must not duplicate an unfinished read.
        pending.current ??= Promise.resolve().then(latest.current.run).finally(()=>{pending.current=null;});
        return pending.current;
      },
      interval: () => typeof latest.current.interval === 'number' ? latest.current.interval : latest.current.interval(),
      hiddenInterval,
      onError: error => latest.current.onError?.(error),
    });
  }, [enabled, hiddenInterval]);
}
