import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { promisify } from "node:util";
import { chromium } from "playwright";

const [schedule, port, destination, runRoot = "/tmp/chat-demo"] = process.argv.slice(2);
const address = `http://127.0.0.1:${port}`;
const container = `minecollab-demo-${schedule}`;
const command = promisify(execFile);
const cache = process.env.DEMO_VIEWER_CACHE;
const probe = `
import json,sys
from pathlib import Path
folder=Path(sys.argv[1])/sys.argv[2]
def read(name):
    p=folder/name
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
chat=[]
log=folder/'agents.log'
if log.exists():
    for line in log.read_text(errors='replace').splitlines():
        if not line.startswith('STUDY '):
            continue
        try:
            row=json.loads(line.removeprefix('STUDY '))
        except ValueError:
            continue
        msg=row.get('message','').strip()
        if row['event']=='chat' and msg and not msg.startswith('!'):
            chat.append([row['sender'],msg])
print(json.dumps({'clock':read('start.json'),'finish':read('finish.json'),'chat':chat[-1:]}))
`;

await fs.mkdir(destination, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.DEMO_CHROME,
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
    "--disable-features=LocalNetworkAccessChecks"],
});
try {
  const readyBy = Date.now() + 140_000;
  while (true) {
    try {
      if ((await fetch(address, { signal: AbortSignal.timeout(1200) })).ok) break;
    } catch {}
    if (Date.now() > readyBy) throw new Error("The Minecraft camera did not start");
    await sleep(400);
  }

  const size = { width: 1440, height: 810 };
  const context = await browser.newContext({ viewport: size, recordVideo: { dir: destination, size } });
  const page = await context.newPage();
  const video = page.video();
  page.on('console', message => console.log('browser', message.type(), message.text().slice(0, 200)));
  page.on('pageerror', error => console.error('pageerror', error.message));
  page.on('requestfailed', req => console.error('requestfailed', req.url(), req.failure()));
  if (cache) {
    for (const asset of ["index.js", "worker.js", "textures/1.21.1.png", "blocksStates/1.21.1.json"]) {
      await page.route(address + "/" + asset, route => route.fulfill({ path: path.join(cache, asset) }));
    }
  }
  await page.route(address + '/', route => route.fulfill({ contentType: "text/html", body: `
<!doctype html>
<meta charset="utf-8">
<style>
  * { box-sizing:border-box } body { margin:0;background:#101d23;color:#f3f7f5;font:22px Arial,sans-serif }
  header { height:112px;padding:17px 25px;display:flex;align-items:center;justify-content:space-between }
  h1 { margin:0 0 7px;font-size:37px } #sub { color:#a6c3c0 }
  #phase { color:#8ee4cb;font-weight:bold } #clock { margin-left:19px;font-variant-numeric:tabular-nums }
  body { overflow:hidden }
  header,footer { position:fixed;left:0;right:0;z-index:2;background:#101d23 }
  header { top:0 }
  footer { bottom:0;padding:13px 25px;height:76px;line-height:1.25;overflow:hidden }
  #chat { color:#d5e8e6 }
</style>
<header><div><h1>MineCollab gameplay demo</h1><div id="sub">Harvest · two agents · eight inventory goals</div></div>
<div><span id="phase">Waiting for trial</span><span id="clock">0:00</span></div></header>
<script src="/index.js"></script>
<footer id="chat">Latest relayed chat will appear here.</footer>
<script>
window.state={};
setInterval(()=>{
 const {clock,finish,chat}=window.state;
 if(!clock) return;
 const elapsed=Math.max(0,(Math.min(finish?.endMs ?? Date.now(),clock.deadlineMs)-clock.startMs)/1000);
 const time=Math.floor(elapsed);
 document.getElementById('clock').textContent=Math.floor(time/60)+':'+String(time%60).padStart(2,'0');
 const open=clock.chatWindowsMs.some(([a,b])=>a<=elapsed*1000 && elapsed*1000<b);
 document.getElementById('phase').textContent=finish
   ? (finish.verifiedCompletionMs ? 'All 8 goals verified' : 'Time limit reached')
   : (${JSON.stringify(schedule)}==='always' ? 'Chat always open' : open ? 'Chat open' : 'Chat closed · independent play');
 if(chat?.length) document.getElementById('chat').textContent=chat[0][0].replace('_0','')+' · '+chat[0][1].slice(0,250);
},150);
</script>
` }));
  await page.goto(address, { waitUntil: "domcontentloaded", timeout: 60_000 });
  const captureStartedMs = Date.now();
  let screenshot = false;
  try {
    const cutoff = Date.now() + 290_000;
    let finished = false;
    while (Date.now() < cutoff) {
      const { stdout } = await command("docker", ["exec", container, "python", "-c", probe, runRoot, schedule]);
      const state = JSON.parse(stdout);
      await page.evaluate(value => { window.state = value; }, state);
      if (state.clock && !screenshot && Date.now() - state.clock.startMs > 9_000) {
        await page.screenshot({ path: path.join(destination, "preview.png") });
        screenshot = true;
      }
      if (state.finish) {
        await fs.writeFile(path.join(destination, "capture.json"), JSON.stringify({ captureStartedMs, ...state }, null, 2));
        await sleep(1100);
        finished = true;
        break;
      }
      await sleep(850);
    }
    if (!finished) throw new Error("The camera never received a terminal trial record");
  } finally {
    await context.close();
    await video.saveAs(path.join(destination, "capture.webm"));
    await video.delete();
  }
} finally {
  await browser.close();
}
