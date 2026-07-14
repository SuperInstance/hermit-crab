#!/usr/bin/env python3
"""hermitd.py - Hermit Crab daemon. NMEA + OCR hybrid."""
from __future__ import annotations
import json,logging,os,sys,time,threading,math,struct,ctypes,socket
from datetime import datetime,timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

WORKSPACE=Path(__file__).parent.resolve();sys.path.insert(0,str(WORKSPACE))
CFG={"interval":5,"heartbeat":3600,"port":8654}
BUFFER_PATH=WORKSPACE/"cold"/"buffer.jsonl"
log=logging.getLogger("hermitd")
live={"current":None,"segment":None,"segment_history":[],"samples":[],"uptime":time.time(),"captures":0,"errors":0}
_live_lock=threading.Lock()
D=chr(176)  # degree symbol

# ── NMEA reader (shared mode Windows API) ──
GENERIC_READ=0x80000000;FILE_SHARE_READ=1;FILE_SHARE_WRITE=2;OPEN_EXISTING=3
INVALID_HANDLE=ctypes.c_void_p(-1).value
kernel32=ctypes.windll.kernel32

_nmea_handle=None; _nmea_lock=threading.Lock()
_nmea_latest={"lat":None,"lon":None,"sog":None,"cog":None,"alt":None,"sats":0,"quality":0,"ts":0}
_nmea_stop=threading.Event()
NMEA_WR=b""

def _open_nmea():
    global _nmea_handle
    # Try TCP splitter first (nmea_splitter.py broadcasts on localhost:6006)
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("127.0.0.1",6006))
        _nmea_handle=s
        log.info("NMEA: connected to TCP splitter on localhost:6006")
        return True
    except Exception as e:
        log.warning(f"NMEA: TCP splitter not available ({e}), trying COM6...")
    # Fallback: shared-mode COM6
    h=kernel32.CreateFileA(b"\\\\.\\COM6",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,None,OPEN_EXISTING,0,None)
    if h==INVALID_HANDLE: log.warning("NMEA: can't open COM6 (locked by TZ Pro)");return False
    _nmea_handle=h
    dcb=ctypes.create_string_buffer(28)
    struct.pack_into('IHHIIHHHHHHBBBBB',dcb,0,28,4800,0,0,0,0,0,0,0,0,8,0,0,0,0)
    kernel32.SetCommState(_nmea_handle,ctypes.byref(dcb))
    to=ctypes.create_string_buffer(20)
    struct.pack_into('IIIII',to,0,100,0,0,0,0)
    kernel32.SetCommTimeouts(_nmea_handle,ctypes.byref(to))
    log.info("NMEA: COM6 open in shared mode")
    return True

def _parse_nmea_line(line: str):
    global _nmea_latest
    if not line or not line.startswith('$'): return
    parts=line.split(',')
    sen=line[1:6]
    try:
        if sen in("GPRMC","GNRMC") and len(parts)>=12:
            if parts[2]!='A': return  # invalid
            lat_s=parts[3];lon_s=parts[5]
            if lat_s and lon_s:
                lat_d=float(lat_s[:2]);lat_m=float(lat_s[2:]);lat_dec=lat_d+lat_m/60
                lon_d=float(lon_s[:3]);lon_m=float(lon_s[3:]);lon_dec=lon_d+lon_m/60
                if parts[4]=='S':lat_dec=-lat_dec
                if parts[6]=='W':lon_dec=-lon_dec
                sog=float(parts[7])if parts[7]else None
                cog=float(parts[8])if parts[8]else None
                _nmea_latest.update({"lat":lat_dec,"lon":lon_dec,"sog":sog,"cog":cog,"ts":time.time()})
        elif sen in("GPGGA","GNGGA") and len(parts)>=15:
            if parts[6]:_nmea_latest["quality"]=int(parts[6])
            if parts[7]:_nmea_latest["sats"]=int(parts[7])
            if parts[9]:_nmea_latest["alt"]=float(parts[9])
    except: pass

def _nmea_reader():
    global NMEA_WR
    acc=b""
    buf=ctypes.create_string_buffer(1024);rd=ctypes.c_uint32(0)
    while not _nmea_stop.is_set():
        if _nmea_handle is None:time.sleep(1);continue
        try:
            if isinstance(_nmea_handle,socket.socket):
                # TCP socket reader
                data=_nmea_handle.recv(4096)
                if not data:
                    log.warning("NMEA: TCP splitter disconnected")
                    time.sleep(5)
                    continue
                acc+=data
            else:
                # COM port reader (Windows file handle)
                r=kernel32.ReadFile(_nmea_handle,buf,1024,ctypes.byref(rd),None)
                if r and rd.value:
                    acc+=buf.raw[:rd.value]
            while b'\n' in acc:
                line,acc=acc.split(b'\n',1)
                try:_parse_nmea_line(line.decode('ascii',errors='replace').strip())
                except:pass
        except socket.timeout:
            pass
        except (ConnectionResetError,BrokenPipeError,ConnectionAbortedError):
            log.warning("NMEA: TCP connection lost, retrying...")
            time.sleep(5)
            _open_nmea()
        except:time.sleep(0.5)

def nmea_sample()->Optional[dict]:
    with _nmea_lock:
        d=dict(_nmea_latest)
    if d.get("lat") is None:return None
    age=time.time()-d["ts"]
    return{"ts":datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "lat":d["lat"],"lon":d["lon"],"sog":d["sog"],
           "cog":d["cog"],"alt":d["alt"],"sats":d["sats"],
           "quality":d["quality"],"source":"nmea","age_s":round(age,1)}

# ── fallback: OCR capture ──
from tzpro_extract import extract,capture_via_powershell
CAPTURE_SCRIPT=WORKSPACE/"capture_monitor2.ps1"

def ocr_sample()->Optional[dict]:
    try:
        r=extract(capture_via_powershell(str(CAPTURE_SCRIPT),log),log=log)
        f=r.fields
        return{"ts":r.capture_timestamp,"lat":f["latitude"]["value"],"lon":f["longitude"]["value"],
               "sog":f["sog"]["value"],"depth":f["depth"]["value"],"tide":f["tide_height"]["value"],
               "chart_scale":f["chart_scale"]["value"],"source":"ocr"}
    except:return None

# ── segment tracking ──
def new_segment(s:dict)->dict:
 return{"id":f"seg_{datetime.now():%Y%m%d_%H%M%S}","start_ts":s["ts"],"start_lat":s["lat"],"start_lon":s["lon"],
        "sog_sum":s["sog"]or 0,"sog_sum_sq":(s["sog"]or 0)**2,"sog_n":1,"samples":1,
        "end_lat":s["lat"],"end_lon":s["lon"],"tide_sum":s.get("tide",0)or 0,
        "chart_scale":s.get("chart_scale"),"sog_base":s["sog"],"sog_sustain":0}
def update_segment(seg:dict,s:dict)->bool:
 seg["samples"]+=1;seg["end_lat"],seg["end_lon"]=s["lat"],s["lon"]
 sg=s["sog"]or 0;seg["sog_sum"]+=sg;seg["sog_sum_sq"]+=sg**2;seg["sog_n"]+=1
 seg["tide_sum"]+=s.get("tide",0)or 0
 if seg["sog_base"]is not None and s["sog"]is not None:
  if abs(s["sog"]-seg["sog_base"])>0.3:seg["sog_sustain"]+=1
  else:seg["sog_sustain"]=0;seg["sog_base"]=s["sog"]
  if seg["sog_sustain"]>=5:return True
 try:start=datetime.fromisoformat(seg["start_ts"]);now=datetime.fromisoformat(s["ts"]);return(now-start).total_seconds()>900
 except:pass
 return False
def close_segment(seg:dict)->dict:
 n=max(seg["sog_n"],1);mean=seg["sog_sum"]/n;var=max(0,seg["sog_sum_sq"]/n-mean**2)
 try:end=datetime.fromisoformat(seg.get("end_ts",seg["start_ts"]));duration_s=int((end-datetime.fromisoformat(seg["start_ts"])).total_seconds())
 except:duration_s=0
 dlat=seg["end_lat"]-seg["start_lat"];dlon=seg["end_lon"]-seg["start_lon"];dist=math.sqrt(dlat**2+(dlon*0.57)**2)*60
 return{"id":seg["id"],"start_ts":seg["start_ts"],"end_ts":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_lat":seg["start_lat"],"start_lon":seg["start_lon"],"end_lat":seg["end_lat"],"end_lon":seg["end_lon"],
        "sog_mean":round(mean,2),"sog_var":round(var,4),"duration_s":duration_s,"distance_nm":round(dist,3),
        "chart_scale":seg.get("chart_scale")}

# ── buffer ──
def buffer_append(s:dict)->None:
 BUFFER_PATH.parent.mkdir(parents=True,exist_ok=True)
 BUFFER_PATH.open("a",encoding="utf-8").write(json.dumps(s,separators=(",",":"))+"\n")
def buffer_flush()->int:
 if not BUFFER_PATH.exists():return 0
 lines=BUFFER_PATH.read_text(encoding="utf-8").strip().split("\n")
 if not lines or not lines[0]:return 0
 entries=[];import subprocess,shutil
 for line in lines:
  try:entries.append(json.loads(line))
  except:pass
 if not entries:return 0
 w=shutil.which("wrangler")or r"C:\Users\casey\AppData\Roaming\npm\wrangler.CMD"
 sql="INSERT OR REPLACE INTO track_points(ts,lat,lon,sog,cog,source,agent_id)VALUES\n";vals=[]
 for e in entries:
  ts=str(e.get("ts","")).replace("'","''")
  lat=e.get("lat","NULL");lon=e.get("lon","NULL")
  sog=e.get("sog","NULL");cog=e.get("cog","NULL")
  src=e.get("source","nmea");vals.append(f"('{ts}',{lat},{lon},{sog},{cog},'{src}','agent:hermit-crab')")
 sql+=",\n".join(vals)+";"
 proc=subprocess.run([w,"d1","execute","hermit-crab-memory-db","--command",sql,"--remote"],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30,cwd=str(WORKSPACE))
 if proc.returncode==0:BUFFER_PATH.write_text("",encoding="utf-8");return len(entries)
 return 0

# ── capture loop ──
def capture_loop(stop):
 seg=None;last_flush=time.time();ocr_count=0
 log.info("Started NMEA+OCR hybrid -- capture every %ds",CFG["interval"])
 while not stop.is_set():
  try:
   t0=time.time()
   # Try NMEA first
   s=nmea_sample()
   # Fall back to OCR for tide/scale every 5th iteration
   if s is None or ocr_count%5==0:
    ocr=ocr_sample()
    if ocr:
     if s is None:
      s=ocr
     else:
      s["depth"]=ocr.get("depth");s["tide"]=ocr.get("tide");s["chart_scale"]=ocr.get("chart_scale")
    ocr_count+=1
   if s:
    with _live_lock:
     live["current"]=s;live["samples"].append(s);live["captures"]+=1
     if len(live["samples"])>300:live["samples"]=live["samples"][-300:]
     if seg is None:seg=new_segment(s)
     else:
      seg["end_ts"]=s["ts"]
      if update_segment(seg,s):
       closed=close_segment(seg)
       with _live_lock:
        live["segment_history"].append(closed)
        if len(live["segment_history"])>20:live["segment_history"]=live["segment_history"][-20:]
       log.info("Segment closed: %s (%.3fnm)",closed["id"],closed["distance_nm"])
       buffer_append({"ts":closed["end_ts"],"event":"segment_close","segment_id":closed["id"],"sog_mean":closed["sog_mean"]})
       seg=new_segment(s)
     buffer_append(s)
    live["segment"]=seg
   if time.time()-last_flush>=CFG["heartbeat"]:
    n=buffer_flush()
    if n:log.info("Heartbeat: flushed %d entries",n);last_flush=time.time()
   stop.wait(max(0.1,CFG["interval"]-(time.time()-t0)))
  except Exception as e:log.error("Loop: %s",e);live["errors"]+=1;stop.wait(5)

# ── HTTP dashboard ──
class DashH(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path not in("/",):self.send_error(404);return
  with _live_lock:c=live["current"];smps=list(live["samples"])
  h=self._page(c,smps).encode("utf-8")
  self.send_response(200);self.send_header("Content-Length",str(len(h)))
  self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(h)
 def _fmt(self,v,lat):
  if v is None:return"---"
  d=int(abs(v));m=(abs(v)-d)*60;mi=int(m);dc=int((m-mi)*1000)
  h="N"if lat and v>=0 else"S"if lat else"W"if v<0 else"E"
  return f"{d}{D}{mi:02d}.{dc:03d}' {h}"
 def _page(self,c,smps):
  if c and c.get("lat"):lat_s=self._fmt(c["lat"],1);lon_s=self._fmt(c["lon"],0)
  else:lat_s=lon_s="---"
  vals=[x["sog"]for x in smps if x.get("sog")is not None];n=len(vals)
  a5=sum(vals[-6:])/max(len(vals[-6:]),1)if vals else 0
  a10=sum(vals[-12:])/max(len(vals[-12:]),1)if len(vals)>=12 else a5
  a20=sum(vals[-20:])/max(len(vals[-20:]),1)if len(vals)>=20 else a10
  sg=f"{a5:.2f}"if a5>0 else"---";ti=f'{c["tide"]:.2f}'if c and c.get("tide")else"---"
  dp=f'{c["depth"]}'if c and c.get("depth")else"---";sc=f'{c["chart_scale"]}'if c and c.get("chart_scale")else"---"
  cg=f'{c["cog"]:.1f}°'if c and c.get("cog")else"---";src=c.get("source","")if c else""
  ts=c["ts"]if c else"---";rows=""
  for x in reversed(smps[-5:]):
   lf=self._fmt(x.get("lat"),1)if x.get("lat")else"---"
   lf2=self._fmt(x.get("lon"),0)if x.get("lon")else"---"
   ss=x.get("sog");ss=f"{ss:.2f}"if isinstance(ss,(int,float))else"---"
   rows+=f"<tr><td>{x['ts'][11:19]}</td><td>{lf}</td><td>{lf2}</td><td>{ss}</td></tr>\n"
  return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="1">
<title>hermit-crab</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'SF Mono','Cascadia Code',monospace;background:#0d1117;color:#c9d1d9;padding:16px}}
.grd{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:6px;margin-bottom:8px}}
.cd{{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px 10px}}
.lb{{font-size:9px;color:#8b949e;text-transform:uppercase}}
.vl{{font-size:20px;font-weight:600;margin-top:1px}}
.cl{{color:#ffa657;font-size:14px}}.cs{{color:#7ee787}}.ct{{color:#79c0ff}}.c2{{color:#d2a8ff}}.cc{{color:#ff7b72}}
.av{{display:flex;gap:14px;margin:6px 0;font-size:12px}}
.av span{{color:#8b949e}}.av b{{color:#7ee787}}
h2{{font-size:11px;color:#8b949e;margin:8px 0 4px;text-transform:uppercase}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{text-align:left;color:#8b949e;padding:3px 6px;border-bottom:1px solid #30363d}}
td{{padding:3px 6px;border-bottom:1px solid #21262d}}
#ft{{margin-top:6px;font-size:9px;color:#484f58}}
</style></head><body>
<div class="grd"><div class="cd"><div class="lb">Lat</div><div class="vl cl">{lat_s}</div></div>
<div class="cd"><div class="lb">Lon</div><div class="vl cl">{lon_s}</div></div>
<div class="cd"><div class="lb">SOG</div><div class="vl cs">{sg} kn</div></div>
<div class="cd"><div class="lb">COG</div><div class="vl cc">{cg}</div></div>
<div class="cd"><div class="lb">Depth</div><div class="vl c2">{dp} fm</div></div>
<div class="cd"><div class="lb">Tide</div><div class="vl ct">{ti} ft</div></div></div>
<div class="av"><span>5s: <b>{a5:.2f}</b></span><span>10s: <b>{a10:.2f}</b></span><span>20s: <b>{a20:.2f}</b> kn ({n} samples)</span><span style="color:#484f58">src:{src}</span></div>
<h2>Last 5 captures</h2><table><tr><th>Time</th><th>Lat</th><th>Lon</th><th>SOG</th></tr>{rows}</table>
<div id="ft">{ts}|cap:{live["captures"]}|up:{int(time.time()-live["uptime"])}s|NMEA+OCR</div></body></html>"""
 def log_message(self,*a):pass

def run_dash(stop):
 s=HTTPServer(("127.0.0.1",CFG["port"]),DashH);log.info(":8%d",CFG["port"])
 while not stop.is_set():s.handle_request()

def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument("--once",action="store_true");p.add_argument("--status",action="store_true");p.add_argument("--flush",action="store_true");p.add_argument("--interval",type=int,default=5);p.add_argument("--heartbeat",type=int,default=3600);p.add_argument("--port",type=int,default=8654);a=p.parse_args()
 logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",datefmt="%H:%M:%S")
 CFG.update(interval=a.interval,heartbeat=a.heartbeat,port=a.port)
 if a.flush:n=buffer_flush();print(f"Flushed {n}");return
 if a.once:s=nmea_sample()or ocr_sample();print(json.dumps(s,default=str)if s else"fail");buffer_append(s);return
 if a.status:
  with _live_lock:print(json.dumps({"current":live["current"],"captures":live["captures"]},indent=2,default=str))
  return
 # Start NMEA splitter (COM6 -> TCP broadcast), then connect reader
 try:
     import subprocess
     splitter_path=WORKSPACE/"nmea_splitter.py"
     if splitter_path.exists():
         sp=subprocess.Popen([sys.executable,str(splitter_path)],
             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
         log.info(f"NMEA splitter started (pid {sp.pid})")
         time.sleep(1)  # let it open COM6
 except Exception as e:
     log.warning(f"Could not start NMEA splitter: {e}")
 if _open_nmea():threading.Thread(target=_nmea_reader,daemon=True).start()
 stop=threading.Event();threading.Thread(target=capture_loop,args=(stop,),daemon=True).start();threading.Thread(target=run_dash,args=(stop,),daemon=True).start()
 print(f"hermitd http://127.0.0.1:{CFG['port']}|{CFG['interval']}s|{CFG['heartbeat']//60}min")
 try:[time.sleep(1)for _ in iter(lambda:not stop.is_set(),True)]
 except KeyboardInterrupt:stop.set();time.sleep(1);n=buffer_flush();print(f"\nFlushed {n}")

if __name__=="__main__":main()
