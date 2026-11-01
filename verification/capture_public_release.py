from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent/'public-release'
for name,width,height in [('desktop',1440,1000),('narrow',600,900)]:
    args=[r'C:\Program Files\Google\Chrome\Application\chrome.exe','--headless','--disable-gpu',
        '--disable-background-networking','--no-first-run','--no-default-browser-check',
        '--user-data-dir='+str(ROOT/('chrome-'+name)),'--window-size='+str(width)+','+str(height),
        '--force-device-scale-factor=1','--virtual-time-budget=1000','--screenshot='+str(ROOT/(name+'.png')),
        '--dump-dom',(ROOT/'preview.html').as_uri()]
    result=subprocess.run(args,capture_output=True,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/(name+'.html')).write_bytes(result.stdout)
    (ROOT/(name+'.log')).write_bytes(result.stderr)
    print(name,result.returncode,(ROOT/(name+'.png')).is_file())
