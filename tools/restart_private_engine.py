"""Migrate the one-time downloader to an offline-only inference process."""
from pathlib import Path
import sys,json,subprocess,os,signal,time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from private_contracts.config import DATA,initialize
from private_contracts.engine import start_engine,status,ollama_binary
initialize()
marker=DATA/'engine.json'
if marker.exists():
    config=json.loads(marker.read_text())
    pid=config.get('pid')
    if pid and not config.get('outbound_restricted'):
        check=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
        command=check.stdout.strip()
        if check.returncode==0:
            if 'ollama' not in command or 'serve' not in command:
                raise RuntimeError('The old process no longer matches this app. It was not stopped.')
            os.kill(pid,signal.SIGTERM)
            time.sleep(1)
print(json.dumps(start_engine(wait=30)),flush=True)
