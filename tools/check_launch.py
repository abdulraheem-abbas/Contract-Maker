from urllib.request import build_opener,ProxyHandler,HTTPCookieProcessor
from http.cookiejar import CookieJar
import json
client=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()))
for route in ['/','/api/ping','/api/bootstrap']:
    try:
        with client.open('http://127.0.0.1:8768'+route,timeout=5) as response:
            raw=response.read()
            item={'route':route,'status':response.status,'bytes':len(raw)}
            if route=='/api/bootstrap':item['model']=json.loads(raw)['engine']['model']
            print(json.dumps(item),flush=True)
    except Exception as exc:
        print(json.dumps({'route':route,'error':str(exc),'kind':type(exc).__name__}),flush=True)
        if hasattr(exc,'read'):print(exc.read().decode()[:300],flush=True)
