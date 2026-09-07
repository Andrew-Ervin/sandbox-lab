// Keep submission ownership until the response stream finishes, including the
// interval before ChatKit emits response.start. Never cancel a background job.
export class ChatTransport {
  pending = new Map<string, symbol>();
  busy(thread: string | null) {
    return this.pending.has(thread || 'new');
  }
  async send(
    fetcher: typeof fetch,
    input: RequestInfo | URL,
    init?: RequestInit,
  ) {
    let request: { type?: string; params?: { thread_id?: string } } = {};
    try {
      if (typeof init?.body === 'string') request = JSON.parse(init.body);
    } catch {}
    if (
      ![
        'threads.create',
        'threads.add_user_message',
        'threads.retry_after_item',
      ].includes(request.type || '')
    )
      return fetcher(input, init);
    let key = request.params?.thread_id || 'new';
    if (this.pending.has(key))
      throw Error(
        'This conversation is already responding. Wait for it to finish or stop the run.',
      );
    const token = Symbol();
    this.pending.set(key, token);
    const release = () => {
      if (this.pending.get(key) === token) this.pending.delete(key);
    };
    try {
      const response = await fetcher(input, init);
      if (!response.ok || !response.body) {
        release();
        return response;
      }
      const reader = response.body.getReader(),
        decoder = new TextDecoder();
      let prefix = '';
      return new Response(
        new ReadableStream<Uint8Array>({
          pull: async (controller) => {
            try {
              const { done, value } = await reader.read();
              if (done) {
                release();
                controller.close();
                return;
              }
              if (key === 'new') {
                prefix += decoder.decode(value, { stream: true });
                for (const line of prefix.split('\n')) {
                  if (!line.startsWith('data: ')) continue;
                  try {
                    const event = JSON.parse(line.slice(6));
                    if (
                      event.type === 'thread.created' &&
                      typeof event.thread?.id === 'string'
                    ) {
                      release();
                      key = event.thread.id;
                      this.pending.set(key, token);
                      prefix = '';
                      break;
                    }
                  } catch {}
                }
                if (prefix.length > 1000000) prefix = '';
              }
              controller.enqueue(value);
            } catch (error) {
              release();
              controller.error(error);
            }
          },
          cancel: async (reason) => {
            release();
            await reader.cancel(reason);
          },
        }),
        {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        },
      );
    } catch (error) {
      release();
      throw error;
    }
  }
}
