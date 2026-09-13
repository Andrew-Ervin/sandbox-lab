"""Configured quick-Python execution; ordinary chat allocates no compute."""
from .azure_adapters import AzureQuick
from .azure_runtime import runtime
from .builtin_python import BuiltinPython
compute = BuiltinPython() if runtime().config.get('builtin_session_endpoint') else AzureQuick()
