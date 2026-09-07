"""Own ChatKit streams independently of HTTP clients; SQLite holds their results."""
import asyncio, json, time, uuid, os

class Jobs:
    def __init__(self, store, concurrency=None):
        self.store = store
        self.tasks = {}
        self.slots = asyncio.Semaphore(concurrency or max(1,int(os.getenv("JOB_CONCURRENCY","8"))))
        self.max_pending=max(1,int(os.getenv("JOB_MAX_PENDING","64")))

    def start(self, stream, context, thread_id=None, *, acknowledge=False):
        if len(self.tasks)>=self.max_pending: raise RuntimeError('The local job queue is full; retry after a running task finishes.')
        job = {'id': 'job_'+uuid.uuid4().hex, 'thread_id': thread_id, 'owner': context['owner'],
               'status': 'queued', 'started': time.time(), 'progress': 'Waiting for capacity'}
        context['job'] = job
        self.store.save_job(job)
        queue = asyncio.Queue(maxsize=64)
        attached = True

        async def produce():
            try:
                iterator=stream.__aiter__()
                if acknowledge:
                    # Persist and acknowledge the user message before waiting for a
                    # worker. ChatKit emits stream_options before invoking respond.
                    async for chunk in iterator:
                        event=json.loads(chunk[6:]) if chunk.startswith(b'data: ') else {}
                        tid=event.get('thread',{}).get('id') or event.get('item',{}).get('thread_id')
                        if tid:job['thread_id']=tid;self.store.save_job(job)
                        if attached:queue.put_nowait(chunk)
                        if event.get('type')=='stream_options':break
                async with self.slots:
                    job.update(status='running', progress='Working')
                    self.store.save_job(job)
                    async for chunk in iterator:
                        if chunk.startswith(b'data: '):
                            previous = dict(job)
                            event = json.loads(chunk[6:])
                            thread = event.get('thread', {})
                            if thread.get('id'): job['thread_id'] = thread['id']
                            if event.get('type') == 'progress_update': job['progress'] = event.get('text', 'Working')
                            if event.get('type') == 'error': job['status'] = 'failed'
                            if job != previous:self.store.save_job(job)
                        if attached:
                            # Never let a slow or disconnected UI block execution/persistence.
                            if queue.full(): queue.get_nowait()
                            queue.put_nowait(chunk)
                    if job['status'] != 'failed': job.update(status='completed', progress='Finished')
            except asyncio.CancelledError:
                job.update(status='canceled', progress='Stopped')
                raise
            except Exception:
                job.update(status='failed', progress='The response failed; check the conversation')
            finally:
                job['finished'] = time.time()
                self.store.save_job(job)
                if queue.full(): queue.get_nowait()
                queue.put_nowait(None)
                self.tasks.pop(job['id'], None)

        self.tasks[job['id']] = asyncio.create_task(produce())

        async def subscribe():
            nonlocal attached
            try:
                while (chunk := await queue.get()) is not None: yield chunk
            finally:
                attached = False  # navigation/disconnect never cancels the producer
        return subscribe()

    def active(self, owner, thread_id):
        return [j for j in self.store.jobs(owner) if j['thread_id'] == thread_id and j['id'] in self.tasks]

    async def stop(self, owner, thread_id):
        tasks = [self.tasks[j['id']] for j in self.active(owner, thread_id)]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
