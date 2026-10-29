#!/usr/bin/env python3
"""Pixiv ranking crawler; network is performed only by run()."""
from __future__ import annotations
import argparse,json,os,random
from datetime import date,datetime,timedelta
from pathlib import Path
import yaml
try:
    from pixivpy3 import AppPixivAPI
except ImportError: AppPixivAPI=None
from selection import choose,is_r18,safe_filename

def load_dotenv(path):
    values={}; path=Path(path)
    candidates=[path, Path(os.getenv("HERMES_HOME", "/opt/data")) / ".env"]
    seen=set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen or not candidate.exists():
            continue
        seen.add(candidate)
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); values[k.strip()]=v.strip().strip("\"'")
                os.environ[k.strip()]=values[k.strip()]
    return values

def load_config(path):
    with Path(path).open(encoding="utf-8") as f: return yaml.safe_load(f) or {}

def historical_dates(count,today=None,rng=None):
    today=today or date.today(); start=date(2020,1,1)
    if today<start:return []
    rng=rng or random.SystemRandom(); available=(today-start).days+1
    chosen=set()
    while len(chosen)<min(max(0,count),available): chosen.add(start+timedelta(days=rng.randrange(available)))
    return sorted(d.isoformat() for d in chosen)

def append_jsonl(path,event,**data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as f: f.write(json.dumps({"ts":datetime.now().isoformat(),"event":event,**data},ensure_ascii=False)+"\n")

def _url(item,page=0):
    urls=item.get("original_urls") or []
    if page<len(urls) and isinstance(urls[page],dict): return urls[page].get("url")
    return (item.get("image_urls") or {}).get("original")

class PixivDailyCrawler:
    def __init__(self,config_path="config.yaml",api=None):
        self.config_path=Path(config_path); load_dotenv(self.config_path.parent/".env"); self.config=load_config(config_path)
        output=self.config.get("output",{}); self.out=Path(os.getenv("PIXIV_DAILY_OUTPUT_DIR",output.get("base_dir","/opt/data/projects/pixiv-daily-crawler/data"))); self.out.mkdir(parents=True,exist_ok=True)
        self.log_path=self.out/f"events_{date.today().isoformat()}.jsonl"; self.state_path=self.out/"dedupe_state.json"; self.api=api
    def authenticate(self):
        token=os.getenv(self.config.get("pixiv",{}).get("refresh_token_env","PIXIV_REFRESH_TOKEN"))
        if not token: raise RuntimeError("PIXIV_REFRESH_TOKEN is not configured")
        if self.api is None:
            if AppPixivAPI is None: raise RuntimeError("pixivpy3 is required for network runs")
            self.api=AppPixivAPI()
        self.api.auth(refresh_token=token)
    def fetch(self,mode,day=None,limit=100):
        result=self.api.illust_ranking(mode=mode,**({"date":day} if day else {})); out=[]
        for rank,w in enumerate(getattr(result,"illusts",[]) or [],1):
            urls=[]; pages=getattr(w,"meta_pages",[]) or []
            for page in range(int(getattr(w,"page_count",1) or 1)):
                meta=getattr(w,"meta_single_page",None) if page==0 else (pages[page] if page<len(pages) else None)
                urls.append({"url":getattr(meta,"original_image_url",None) if meta else None,"page":page,"width":getattr(w,"width",0),"height":getattr(w,"height",0)})
            out.append({"id":getattr(w,"id",None),"title":getattr(w,"title","untitled"),"user":{"name":getattr(getattr(w,"user",None),"name","unknown")},"tags":[getattr(t,"name","") for t in getattr(w,"tags",[]) or []],"total_bookmarks":getattr(w,"total_bookmarks",0),"total_view":getattr(w,"total_view",0),"page_count":getattr(w,"page_count",1),"type":getattr(w,"type","illust"),"ai_type":getattr(w,"illust_ai_type",0),"create_date":str(getattr(w,"create_date","")),"rank":rank,"source_ranking_mode":mode,"source_weight":(self.config.get("crawler",{}).get("source_weights") or {}).get(mode,1.0),"is_r18":mode.endswith("r18"),"original_urls":urls})
        return out
    def run(self):
        self.authenticate(); cfg=self.config.get("crawler",{}); modes=cfg.get("modes",[])+cfg.get("r18_modes",[]); items=[]
        recent_modes=modes[:]
        for mode in recent_modes:
            try:
                    batch = self.fetch(mode, limit=int(cfg.get("limit_per_mode", 100)))
                    for item in batch:
                        item["source_period"] = "recent"
                    items.extend(batch)
                    append_jsonl(self.log_path, "fetch", mode=mode, period="recent", status="ok")
            except Exception as e:
                append_jsonl(self.log_path, "fetch", mode=mode, period="recent", status="error", error=type(e).__name__)
        for day in historical_dates(int(cfg.get("historical_count", 4))):
            for mode in modes:
                try:
                    batch = self.fetch(mode, day, int(cfg.get("limit_per_mode", 100)))
                    for item in batch:
                        item["source_period"] = "historical"
                    items.extend(batch)
                    append_jsonl(self.log_path, "fetch", mode=mode, date=day, period="historical", status="ok")
                except Exception as e:
                    append_jsonl(self.log_path, "fetch", mode=mode, date=day, status="error", error=type(e).__name__)
        selected,filtered=choose(items,cfg)
        for x in filtered: append_jsonl(self.log_path,"filter",id=x.get("id"),reason=x.get("filter_reason"))
        state=json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {"ids":[],"urls":[],"filenames":[]}; ids=set(map(str,state.get("ids",[]))); urls=set(state.get("urls",[])); names=set(state.get("filenames",[])); records=[]
        old_names=set(state.get("filenames",[]))
        for x in selected:
            u=_url(x); proposed=safe_filename(x,set())
            if str(x.get("id")) in ids or (u and u in urls) or proposed in old_names:
                append_jsonl(self.log_path,"dedupe",id=x.get("id"),url=u,status="skip"); continue
            x=dict(x); name=safe_filename(x,names); x["filename"]=name; x["remote_filename"]=name; x["pool"]="r18" if is_r18(x) else "normal"; records.append(x); ids.add(str(x.get("id"))); 
            if u: urls.add(u)
            names.add(name); append_jsonl(self.log_path,"select",id=x.get("id"),url=u,pool=x["pool"],score=x.get("score"),filename=name)
        today=date.today().isoformat(); (self.out/f"new_items_{today}.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8"); self.state_path.write_text(json.dumps({"ids":sorted(ids),"urls":sorted(urls),"filenames":sorted(names)},ensure_ascii=False,indent=2),encoding="utf-8"); report={"generated_at":datetime.now().isoformat(),"selected":len(records),"normal":sum(x["pool"]=="normal" for x in records),"r18":sum(x["pool"]=="r18" for x in records),"filtered":len(filtered),"fetched":len(items)}; (self.out/f"run_report_{today}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); return records

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    args=p.parse_args()
    PixivDailyCrawler(args.config).run()
    return 0
if __name__=="__main__": raise SystemExit(main())
# Legacy Top3/Top5 senders are retired; use daily_run.py.
