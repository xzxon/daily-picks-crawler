#!/bin/bash
# Pixiv daily crawl on VPS + handoff package for Orange Pi pickup
set -u
export HOME=/root
PROJ=/opt/pixiv-daily
OUT=$PROJ/output
TODAY=$(date +%F)
LOG=$OUT/cron_$TODAY.log
LOCK=/tmp/pixiv_crawl.lock

exec 9>$LOCK || exit 0
flock -n 9 || exit 0  # previous run still going

{
cd $PROJ
python3 daily_run.py --crawl-only
CRAWL_EXIT=$?
if [ $CRAWL_EXIT -ne 0 ]; then echo "[$(date '+%F %T')] crawl failed exit=$CRAWL_EXIT"; exit 1; fi
# package only today's downloads + reports for pickup
tar czf /tmp/pixiv_out_$TODAY.tar.gz -C $OUT downloads run_report_$TODAY.json new_items_$TODAY.json 2>/dev/null
echo "[$(date '+%F %T')] CRAWL_OK package=/tmp/pixiv_out_$TODAY.tar.gz"
} >> $LOG 2>&1
