"""Lifecycle status facade; Azure owns all idle decisions."""
import asyncio
class IdleWorkspaces:
    def __init__(self,headless,developer,previews):
        self.project_idle=600;self.developer_idle=600;self.error=None;self.stopped=0
    async def maintain(self): await asyncio.Event().wait()
