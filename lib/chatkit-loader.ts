let loading: Promise<void> | undefined;
export function loadChatKit(): Promise<void> {
  if (customElements.get('openai-chatkit')) return Promise.resolve();
  if (loading) return loading;
  loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.platform.openai.com/deployments/chatkit/chatkit.js';
    script.async = true;
    const timer = setTimeout(() => fail(), 20000);
    const fail = () => { clearTimeout(timer); script.remove(); loading = undefined; reject(Error('Chat could not load. Please retry.')); };
    script.onerror = fail;
    script.onload = () => {
      if (!customElements.get('openai-chatkit')) return fail();
      clearTimeout(timer); resolve();
    };
    document.head.appendChild(script);
  });
  return loading;
}
