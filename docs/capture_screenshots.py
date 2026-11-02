"""Capture only this project's offline documentation scenes, not live Orca UI."""
from pathlib import Path
import html
import json
import re
import subprocess

root=Path(__file__).resolve().parents[1]
scenes=root/'verification/readme'
output=root/'docs/images'
output.mkdir(parents=True,exist_ok=True)
for name in ('overview','materials','objects','swap','connection'):
    width,height=(1600,1180) if name=='overview' else (1440,1080)
    args=[r'C:\Program Files\Google\Chrome\Application\chrome.exe','--headless','--disable-gpu',
          '--disable-background-networking','--no-first-run','--no-default-browser-check',
          '--user-data-dir='+str(scenes/('chrome-'+name)),f'--window-size={width},{height}',
          '--force-device-scale-factor=1','--virtual-time-budget=1600',
          '--screenshot='+str(output/(name+'.png')),'--dump-dom',(scenes/(name+'.html')).as_uri()]
    result=subprocess.run(args,capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
    (scenes/(name+'-rendered.html')).write_bytes(result.stdout)
    (scenes/(name+'.log')).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError('Chrome failed for '+name)
    match=re.search(r'data-doc-report="([^"]+)"',result.stdout.decode('utf-8'))
    assert match,name+' did not finish rendering'
    report=json.loads(html.unescape(match[1]))
    assert report['synthetic'] is True and report['scroll']<=report['width'],report
    expected={'materials':'settingsDialog','objects':'objectsDialog','swap':'swapDialog','connection':'connectionDialog'}
    assert report['dialog']==expected.get(name),report
    print(name,(output/(name+'.png')).stat().st_size,report['dialog'] or 'dashboard')
