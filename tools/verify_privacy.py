"""Test the runtime network restrictions without opening employee documents."""
import sys,subprocess,json,socket
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from private_contracts.engine import MAC_NETWORK_PROFILE,status
listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
port=listener.getsockname()[1]
code='''import socket,sys
s=socket.socket();s.settimeout(3)
try:s.connect(("1.1.1.1",443))
except PermissionError:pass
else:raise AssertionError("Outbound denial was not demonstrated")
s.close()
s=socket.socket();s.settimeout(3);s.connect(("127.0.0.1",int(sys.argv[1])));s.close()
print("outbound denied; loopback allowed")'''
result=subprocess.run(['/usr/bin/sandbox-exec','-p',MAC_NETWORK_PROFILE,sys.executable,'-c',code,str(port)],capture_output=True,text=True)
listener.close()
if result.returncode:raise RuntimeError(result.stderr)
engine=status();assert engine['local_only'] and engine['model_ready']
report={'runtime_outbound':'blocked by macOS','loopback':'allowed','engine_cloud':'disabled','engine_model_ready':True}
(Path(__file__).resolve().parent.parent/'test-results/privacy-check.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
