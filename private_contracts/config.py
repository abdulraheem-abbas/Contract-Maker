from pathlib import Path
import json
import os
import sys

if getattr(sys, 'frozen', False):
    RESOURCES = Path(sys._MEIPASS)
    executable = Path(sys.executable).resolve()
    ROOT = executable.parents[3] if '.app/' in str(executable) else executable.parent
else:
    ROOT = Path(__file__).resolve().parent.parent
    RESOURCES = ROOT
DATA = Path(os.environ.get('PRIVATE_CONTRACTS_DATA', str(ROOT / 'data'))).resolve()
MODEL = 'qwen3-vl:2b-instruct'
try:
    selected=json.loads((DATA/'model-choice.json').read_text()).get('model',MODEL)
    if selected in {'qwen3-vl:2b-instruct','qwen3-vl:4b-instruct'}:MODEL=selected
except (OSError,ValueError):
    pass
if os.environ.get('PRIVATE_CONTRACTS_MODEL') in {'qwen3-vl:2b-instruct','qwen3-vl:4b-instruct'}:
    MODEL=os.environ['PRIVATE_CONTRACTS_MODEL']
ENGINE_PORT = 11435
ENGINE_URL = f'http://127.0.0.1:{ENGINE_PORT}'
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.jpg', '.jpeg', '.png', '.ods', '.xlsx', '.csv', '.txt'}

def initialize():
    os.umask(0o077)
    for folder in ['', 'sources', 'templates', 'outputs', 'cache', 'models', 'logs', 'tessdata']:
        p = DATA / folder
        p.mkdir(parents=True, exist_ok=True)
        try:
            p.chmod(0o700)
        except OSError:
            pass
