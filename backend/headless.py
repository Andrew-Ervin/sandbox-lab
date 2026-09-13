"""The Azure headless project provider."""
from .azure_adapters import AzureProjects
from .azure_transport import AzureError
class HeadlessAPIError(AzureError):
    def __init__(self,status,message=''):
        super().__init__('workspace operation',status)

headless = AzureProjects()
