// Serialize SDK navigation. A slow old selection may finish, but cannot become
// the final selection or dismiss the current transition's loading indicator.
export class ThreadNavigation {
  version = 0;
  requested: string | null = null;
  private tail: Promise<void> = Promise.resolve();
  select(id: string | null, navigate: (id: string | null) => Promise<void>, settled: (error?: Error) => void) {
    const version = ++this.version;
    this.requested = id;
    this.tail = this.tail.catch(() => {}).then(async () => {
      if (version !== this.version) return;
      try {
        await navigate(id);
        if (version === this.version) settled();
      } catch (error) {
        if (version === this.version) settled(error instanceof Error ? error : new Error(String(error)));
      }
    });
    return this.tail;
  }
}
