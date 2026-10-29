#!/usr/bin/env python3
"""Orchestrate crawl, download, upload and exactly one text-only QQ report.

Split-run architecture (China-network friendly):
  --crawl-only : fetch from Pixiv + download locally (Pixiv needs an unblocked
                 network; run this on the VPS), then leave files for pickup.
  default      : upload the previously downloaded files to the configured S3
                  endpoint with size verification and send one text-only QQ report
                 (OpenList's Cloudflare challenges datacenter IPs, so run this
                 from a residential/exempt network).
"""
from __future__ import annotations
import argparse,json,os,subprocess,sys
from datetime import date
from pathlib import Path
import requests
from crawler import PixivDailyCrawler,load_dotenv,load_config,append_jsonl,_url
from selection import is_r18
PROJECT=Path(__file__).resolve().parent

def download_items(items,out,crawler):
 out.mkdir(parents=True,exist_ok=True); done=[]
 for item in items:
  url=_url(item)
  if not url: append_jsonl(crawler.log_path,'download',id=item.get('id'),status='no_url');continue
  path=out/item['filename']
  try:
   with requests.get(url,headers={'Referer':'https://www.pixiv.net/','User-Agent':'Mozilla/5.0'},stream=True,timeout=90) as r:
    r.raise_for_status()
    with path.open('wb') as f:
     for chunk in r.iter_content(1024*1024):
      if chunk:f.write(chunk)
   append_jsonl(crawler.log_path,'download',id=item.get('id'),url=url,status='ok',file=str(path));done.append(path)
  except Exception as e:append_jsonl(crawler.log_path,'download',id=item.get('id'),status='error',error=type(e).__name__)
 return done

def send_one_text(report):
 load_dotenv(Path(os.getenv('HERMES_HOME', '/opt/data'))/'.env'); chat=os.getenv('QQ_CHAT_ID')
 if not chat:return 1
 text=f"📸 Pixiv 每日归档\n作品：{report.get('selected',0)}（普通 {report.get('normal',0)} / R-18 {report.get('r18',0)}）\n过滤：{report.get('filtered',0)}，抓取：{report.get('fetched',0)}"
 hermes=os.getenv('HERMES_BIN','/opt/hermes/bin/hermes'); channel=os.getenv('QQ_CHANNEL','qq')
 if channel == 'qq': channel = 'qqbot'
 target=chat if chat.startswith(channel+':') else f'{channel}:{chat}'
 try:
  return subprocess.run([hermes,'send','--to',target,'--quiet',text],cwd=PROJECT,check=False,capture_output=True).returncode
 except FileNotFoundError:
  return 1

def crawl_only(a):
 c=PixivDailyCrawler(a.config);items=c.run();out=c.out/'downloads'
 normal=download_items([x for x in items if not is_r18(x)],out/'normal',c)
 adult=download_items([x for x in items if is_r18(x)],out/'R-18',c)
 print(f"CRAWL_DONE normal={len(normal)} r18={len(adult)} out={c.out}")
 return 0

def upload_and_notify(a):
 c=PixivDailyCrawler(a.config);out=c.out/'downloads'
 ni=c.out/f'new_items_{date.today().isoformat()}.json'
 want={r['filename']:r['pool'] for r in json.loads(ni.read_text(encoding='utf-8'))} if ni.exists() else {}
 normal=sorted(out/'normal'/f for f in want if want[f]=='normal' and (out/'normal'/f).exists()) if out else []
 adult=sorted(out/'R-18'/f for f in want if want[f]=='r18' and (out/'R-18'/f).exists()) if out else []
 upload_rc=0
 if not a.skip_upload:
  uploader=str(PROJECT/'upload_s3.py')
  rc1=subprocess.run([sys.executable,uploader,*map(str,normal),'--remote-dir','Hermes/pixiv','--log',str(c.log_path)],cwd=PROJECT,check=False).returncode if normal else 0
  rc2=subprocess.run([sys.executable,uploader,*map(str,adult),'--remote-dir','Hermes/pixiv/R-18','--log',str(c.log_path)],cwd=PROJECT,check=False).returncode if adult else 0
  json_files=[c.out/f'new_items_{date.today().isoformat()}.json',c.out/f'run_report_{date.today().isoformat()}.json',c.out/f'top5_{date.today().isoformat()}.json']
  json_files=[p for p in json_files if p.is_file()]
  rc3=subprocess.run([sys.executable,uploader,*map(str,json_files),'--remote-dir','Hermes/pixiv/json','--log',str(c.log_path)],cwd=PROJECT,check=False).returncode if json_files else 0
  upload_rc=max(rc1,rc2,rc3)
  if upload_rc:append_jsonl(c.log_path,'upload_batch',status='partial',normal_rc=rc1,r18_rc=rc2,json_rc=rc3)
 if not a.skip_send:
  rp=c.out/f'run_report_{date.today().isoformat()}.json'
  rep=json.loads(rp.read_text(encoding='utf-8')) if rp.exists() else {}
  if rep.get('selected'):send_one_text(rep)
 return upload_rc

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--config',default=str(PROJECT/'config.yaml'))
 p.add_argument('--skip-upload',action='store_true')
 p.add_argument('--skip-send',action='store_true')
 p.add_argument('--crawl-only',action='store_true',help='fetch from Pixiv + download only (run on VPS)')
 a=p.parse_args();load_dotenv(PROJECT/'.env')
 if a.crawl_only:return crawl_only(a)
 return upload_and_notify(a)
if __name__=='__main__':raise SystemExit(main())
