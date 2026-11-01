from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import signal
import time
import urllib.error
import urllib.request
from .config import DATA, ROOT, MODEL, ENGINE_URL, ENGINE_PORT

class EngineError(ValueError):
    pass

def ollama_binary():
    candidates=[ROOT/'runtime/ollama',Path('/Applications/Ollama.app/Contents/Resources/ollama'),Path(shutil.which('ollama') or '/nonexistent')]
    return next((str(p) for p in candidates if p.is_file()),None)

def request(endpoint, body=None, timeout=15):
    if not endpoint.startswith('/api/') or '..' in endpoint:
        raise EngineError('Invalid local engine request.')
    # The engine is fixed to plain HTTP loopback. Construct only HTTP handlers:
    # no proxy discovery, TLS certificate lookup, file/FTP handlers or redirects.
    opener=urllib.request.OpenerDirector()
    for handler in [urllib.request.ProxyHandler({}),urllib.request.HTTPHandler(),urllib.request.HTTPDefaultErrorHandler(),urllib.request.HTTPErrorProcessor()]:opener.add_handler(handler)
    payload=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(ENGINE_URL+endpoint,data=payload,headers={'Content-Type':'application/json'},method='GET' if body is None else 'POST')
    try:
        with opener.open(req,timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        raise EngineError('The local AI engine is unavailable or took too long. Your files remain local; no cloud fallback is used.') from exc

def status():
    verified=False
    try:
        config=json.loads((DATA/'engine.json').read_text())
        verified=bool(config.get('cloud_disabled') and config.get('outbound_restricted') and config.get('model_directory')==str(DATA/'models') and config.get('port')==ENGINE_PORT)
    except (OSError,ValueError):
        pass
    try:
        version=request('/api/version',timeout=2).get('version','')
        models=request('/api/tags',timeout=2).get('models',[])
        available=any(m.get('name')==MODEL for m in models)
        return {'running':True,'model_ready':available and verified,'model':MODEL,'version':version,'local_only':verified,'url':ENGINE_URL}
    except EngineError:
        return {'running':False,'model_ready':False,'model':MODEL,'local_only':False,'url':ENGINE_URL}

_owned_process=None

MAC_NETWORK_PROFILE='''(version 1)
(allow default)
(deny network-outbound)
(allow network-outbound (remote ip "localhost:*"))
'''

def private_command(binary):
    if sys.platform=='darwin':
        sandbox=Path('/usr/bin/sandbox-exec')
        if not sandbox.exists():
            raise EngineError('The macOS network restriction tool is unavailable. The private engine was not started.')
        return [str(sandbox),'-p',MAC_NETWORK_PROFILE,binary,'serve']
    # Windows packaging supplies an outbound firewall block for Ollama. Until
    # explicitly configured, refuse an unverified private setup.
    if sys.platform=='win32' and os.environ.get('PRIVATE_CONTRACTS_FIREWALL_READY')!='1':
        raise EngineError('Finish the Windows offline firewall setup before starting the AI engine.')
    return [binary,'serve']

def stop_owned_engine():
    marker=DATA/'engine.json'
    if not marker.exists():return
    config=json.loads(marker.read_text())
    if config.get('port')!=ENGINE_PORT or config.get('model_directory')!=str(DATA/'models'):
        raise EngineError('The running engine does not match this app’s private configuration.')
    pid=config.get('pid')
    if sys.platform=='darwin':
        result=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{ENGINE_PORT}','-sTCP:LISTEN','-t'],capture_output=True,text=True)
        matches=result.stdout.strip().splitlines()
        if matches:pid=int(matches[0])
    if pid:
        result=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
        command=result.stdout.strip()
        if result.returncode==0:
            if 'ollama' not in command or 'serve' not in command:
                raise EngineError('The process on the private AI port is unfamiliar. It was not stopped.')
            os.kill(pid,signal.SIGTERM)
            time.sleep(1)

def start_engine(wait=15):
    global _owned_process
    current=status()
    if current['running']:
        # Only accept a server on the dedicated app port if it was started by
        # this app/setup and its no-cloud configuration was recorded.
        marker=DATA/'engine.json'
        if not marker.exists():
            raise EngineError('The private engine port is already in use. Close that server and restart this app.')
        config=json.loads(marker.read_text())
        if not config.get('cloud_disabled') or config.get('model_directory')!=str(DATA/'models') or not config.get('outbound_restricted'):
            raise EngineError('The private engine configuration could not be verified.')
        return current
    binary=ollama_binary()
    if not binary:
        raise EngineError('Install Ollama locally, then restart Private Contracts. No cloud service is required.')
    env=dict(os.environ)
    for key in list(env):
        if key.upper().endswith('_PROXY'):
            del env[key]
    env.update({'OLLAMA_HOST':f'127.0.0.1:{ENGINE_PORT}','OLLAMA_MODELS':str(DATA/'models'),'OLLAMA_NO_CLOUD':'1','OLLAMA_CONTEXT_LENGTH':'4096','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_KEEP_ALIVE':'30s','OLLAMA_FLASH_ATTENTION':'1'})
    log=open(DATA/'logs/engine.log','ab')
    setup_download=os.environ.get('PRIVATE_CONTRACTS_MODEL_DOWNLOAD')=='1'
    command=[binary,'serve'] if setup_download else private_command(binary)
    _owned_process=subprocess.Popen(command,env=env,stdout=log,stderr=log,start_new_session=True)
    log.close()
    deadline=time.monotonic()+wait
    while time.monotonic()<deadline:
        time.sleep(0.3)
        if _owned_process.poll() is not None:
            raise EngineError('The private AI engine did not start. See the local setup status.')
        current=status()
        if current['running']:
            (DATA/'engine.json').write_text(json.dumps({'cloud_disabled':True,'outbound_restricted':not setup_download,'model_directory':str(DATA/'models'),'port':ENGINE_PORT,'pid':_owned_process.pid},indent=2))
            return status()
    raise EngineError('The private AI engine is still starting. Try again shortly.')

def assert_local_model():
    info=request('/api/show',{'model':MODEL})
    if info.get('remote_host') or info.get('remote_model') or info.get('details',{}).get('remote_host'):
        raise EngineError('A remote model was refused. Only downloaded models are allowed.')
    if 'cloud' in MODEL.lower():
        raise EngineError('Cloud models are disabled.')
    return info

def chat(messages, schema, max_tokens=1700):
    current=start_engine()
    if not current['model_ready']:
        raise EngineError('The local model is not downloaded yet. Finish the one-time model download, or enter confirmed fields manually.')
    assert_local_model()
    result=request('/api/chat',{'model':MODEL,'messages':messages,'format':schema,'stream':False,'keep_alive':'30s','think':False,'options':{'temperature':0,'num_ctx':4096,'num_predict':max_tokens}},timeout=600)
    content=result.get('message',{}).get('content','')
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise EngineError('The local model returned an incomplete response. No values were silently accepted.') from exc
