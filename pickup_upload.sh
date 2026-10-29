#!/bin/bash
# Orange Pi side: pick up crawl package from VPS, upload to OpenList, notify QQ
set -u
PROJ=/mnt/TF/DATA/hermes-workspace/pixiv-daily-crawler
TODAY=$(date +%F)
LOG=$PROJ/output/pickup_$TODAY.log
LOCK=/tmp/pixiv_pickup.lock
SSHPASS_FILE=/root/.hermes/secrets/vps_sshpass
VPS_HOST="${VPS_HOST:-}"
VPS_USER="${VPS_USER:-root}"
if [ -z "$VPS_HOST" ]; then echo "缺少 VPS_HOST 环境变量" >&2; exit 1; fi

exec 9>$LOCK || exit 0
flock -n 9 || exit 0

{
# wait for VPS package (up to ~40 min after 11:00 crawl start)
PKG=/tmp/pixiv_out_$TODAY.tar.gz
for i in $(seq 1 20); do
  export SSHPASS=$(cat $SSHPASS_FILE)
  if sshpass -e ssh -o ConnectTimeout=15 ${VPS_USER}@${VPS_HOST} "test -s $PKG"; then break; fi
  sleep 120
done
if ! sshpass -e ssh -o ConnectTimeout=15 ${VPS_USER}@${VPS_HOST} "test -s $PKG"; then
  echo "[$(date '+%F %T')] no package from VPS today"; 
  hermes send --to qqbot --quiet "⚠️ Pixiv 每日抓取：VPS 未产出今日包，请检查" || true
  exit 1
fi
mkdir -p $PROJ/output
sshpass -e scp -q ${VPS_USER}@${VPS_HOST}:$PKG /tmp/ && tar xzf /tmp/pixiv_out_$TODAY.tar.gz -C $PROJ/output/
sshpass -e ssh ${VPS_USER}@${VPS_HOST} "rm -f $PKG"
cd $PROJ
python3 daily_run.py
echo "[$(date '+%F %T')] PICKUP_DONE"
} >> $LOG 2>&1
