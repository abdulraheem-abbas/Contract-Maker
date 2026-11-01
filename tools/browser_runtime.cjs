// Development-only browser runtime; never used for employee document processing.
const os=require('os');
const path=require('path');
let runtime;
try {
  runtime=require('playwright');
} catch (error) {
  const bundled=path.join(os.homedir(),'.cache','codex-runtimes','codex-primary-runtime','dependencies','node','node_modules','playwright');
  runtime=require(bundled);
}
module.exports=runtime;
