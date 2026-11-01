"""One-time download. This program receives no employee documents."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import json
import os
import urllib.request
from private_contracts.config import initialize,DATA,MODEL,ENGINE_URL
from private_contracts.engine import start_engine,status,stop_owned_engine

initialize()
stop_owned_engine()
os.environ['PRIVATE_CONTRACTS_MODEL_DOWNLOAD']='1'
start_engine(wait=30)
print('Private local engine started with cloud features disabled.',flush=True)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
request=urllib.request.Request(ENGINE_URL+'/api/pull',data=json.dumps({'model':MODEL,'stream':True}).encode(),headers={'Content-Type':'application/json'})
last_percent=-1
try:
    with opener.open(request,timeout=600) as response:
        for raw in response:
            item=json.loads(raw)
            if item.get('error'):
                raise RuntimeError('The software download was interrupted. Saved chunks can be resumed by running setup again.')
            total=item.get('total',0)
            complete=item.get('completed',0)
            percent=int(100*complete/total) if total else None
            state={'status':item.get('status',''),'percent':percent,'completed':complete,'total':total,'model':MODEL}
            (DATA/'download-status.json').write_text(json.dumps(state))
            if percent is None or percent//5!=last_percent//5:
                print(json.dumps(state),flush=True)
                if percent is not None:last_percent=percent
    (DATA/'model-choice.json').write_text(json.dumps({'model':MODEL}))
finally:
    stop_owned_engine()
    os.environ.pop('PRIVATE_CONTRACTS_MODEL_DOWNLOAD',None)
    print(json.dumps(start_engine(wait=30)),flush=True)
