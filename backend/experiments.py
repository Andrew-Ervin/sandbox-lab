"""Optional local experiments. Production/source exports work without private demo files."""
import importlib
import os
import sys
from .config import ROOT, STATE

class DisabledExperiment:
    enabled = False
    TOOLS = ()
    NAMES = frozenset()
    INSTRUCTION = ''

    def rebuild_card(self, value):
        return None

    def thread_context(self, thread):
        return ''

    def install(self, app, sessions, store):
        pass

    def configure_gui(self, workspace_id):
        pass

    def prepare_agent_request(self, request):
        return request

    def agent_wrapper(self):
        return "import runpy,sys; sys.path.insert(0,'/opt/lab'); runpy.run_path('/opt/lab/agent.py',run_name='__main__')"

class LocalExperiment(DisabledExperiment):
    enabled = True

    def __init__(self, directory):
        self.directory = directory
        if not (directory / 'live_bridge.py').is_file():
            raise RuntimeError('LAB_ENABLE_MCP_EXPERIMENT is enabled but its private files are missing. Disable it to start normally.')
        # Only a trusted local operator can enable this plugin; no code is downloaded.
        sys.path.insert(0, str(directory))
        try:
            self.bridge = importlib.import_module('live_bridge')
            self.gui = importlib.import_module('gui_setup')
        finally:
            sys.path.remove(str(directory))
        self.TOOLS = self.bridge.TOOLS
        self.NAMES = self.bridge.NAMES
        self.INSTRUCTION = self.bridge.INSTRUCTION

    def __getattr__(self, name):
        return getattr(self.bridge, name)

    def rebuild_card(self, value):
        return self.bridge.rebuild_card(value)

    def thread_context(self, thread):
        return self.bridge.thread_context(thread)

    def install(self, app, sessions, store):
        self.bridge.install(app, sessions, store)

    def configure_gui(self, workspace_id):
        self.gui.install(workspace_id)

    def prepare_agent_request(self, request):
        return self.bridge.prepare_agent_request(request)

    def agent_wrapper(self):
        return (self.directory / 'agent_wrapper.py').read_text()


def load_experiment():
    if os.getenv('LAB_ENABLE_MCP_EXPERIMENT', 'false').lower() != 'true':
        return DisabledExperiment()
    return LocalExperiment(STATE / 'mcp-approval-experiment')

experiment = load_experiment()
