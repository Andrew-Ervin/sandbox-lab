"""Create a local VSIX for the reviewed upstream bundle; no marketplace dependency."""
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import json
root=Path(__file__).resolve().parents[1]/'sandbox/pi-chat';m=json.loads((root/'package.json').read_text())
manifest=f'''<?xml version="1.0" encoding="utf-8"?><PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata><Identity Language="en-US" Id="{m['name']}" Version="{m['version']}" Publisher="{m['publisher']}"/><DisplayName>Pi Chat</DisplayName><Description xml:space="preserve">Pi Chat through Ori for Sandbox Lab</Description><Tags>Chat</Tags><Categories>Other</Categories><GalleryFlags>Public</GalleryFlags><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.98.0"/><Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value=""/><Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value=""/></Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>'''
with ZipFile(root/'pi-chat.vsix','w',ZIP_DEFLATED) as z:
 def add(name,data):
  entry=ZipInfo(name,(2026,9,6,0,0,0));entry.compress_type=ZIP_DEFLATED;entry.external_attr=0o644<<16;z.writestr(entry,data)
 add('extension.vsixmanifest',manifest)
 add('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>')
 for p in sorted(root.rglob('*')):
  if p.is_file() and p.suffix!='.vsix':add('extension/'+str(p.relative_to(root)),p.read_bytes())
