import argparse
import hashlib
import http.client
import json
import os
import sys
import webbrowser
from .config import DATA,initialize
from .server import serve

def existing_instance():
    try:
        entry=json.loads((DATA/'app-address.json').read_text())
        from urllib.parse import urlparse
        url=urlparse(entry['url'])
        if url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port:return None
        conn=http.client.HTTPConnection('127.0.0.1',url.port,timeout=2)
        conn.request('GET','/api/ping',headers={'Host':f'127.0.0.1:{url.port}'})
        result=json.loads(conn.getresponse().read());conn.close()
        if result.get('application')=='Private Contracts' and result.get('data_id')==hashlib.sha256(str(DATA).encode()).hexdigest():return entry['url']
    except (OSError,ValueError,http.client.HTTPException):pass
    return None

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--diagnose',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    initialize()
    if args.diagnose:
        from .privacy import install_network_guard
        install_network_guard()
        from . import store,engine,templates,readers,office
        from .server import rules
        for label,operation in [('workspaces',store.jobs),('templates',templates.registry),('rules',rules),('engine',engine.status),('ocr',readers.tesseract_binary),('office',office.office_binary)]:
            try:operation();print(label+': ok',flush=True)
            except Exception:
                import traceback
                print(label+': failed',flush=True);traceback.print_exc()
        return
    existing=existing_instance()
    if existing:
        if not args.no_browser:webbrowser.open(existing)
        elif sys.stdout is not None:print(existing)
        return
    serve(args.port,not args.no_browser)

if __name__=='__main__':main()
