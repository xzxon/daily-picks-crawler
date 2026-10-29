#!/bin/bash
# 设置 Pixiv 每日抓取的 cron 定时任务

set -e

PROJECT_DIR="/opt/data/projects/pixiv-daily-crawler"
CRON_JOB="0 9 * * * cd $PROJECT_DIR && /usr/bin/python3 daily_run.py >> /var/log/pixiv_crawler.log 2>&1"

echo "🔧 正在设置 cron 定时任务..."
echo "任务: 每日 09:00 抓取 Pixiv 日榜并发送 Top 3"
echo "项目目录: $PROJECT_DIR"
echo "日志: /var/log/pixiv_crawler.log"

# 检查是否已存在
if crontab -l 2>/dev/null | grep -q "$PROJECT_DIR"; then
    echo "⚠️  cron 任务已存在，将先移除旧条目..."
    (crontab -l 2>/dev/null | grep -v "$PROJECT_DIR") | crontab -
fi

# 添加新任务
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
echo "✅ cron 任务已添加"

# 确保日志目录存在
mkdir -p /var/log
touch /var/log/pixiv_crawler.log
chmod 644 /var/log/pixiv_crawler.log

echo "📊 当前用户的 cron 任务列表："
crontab -l

echo "🎉 设置完成！"
echo "手动测试立即运行一次："
echo "  cd $PROJECT_DIR && python3 daily_run.py"
echo ""
echo "查看日志："
echo "  tail -f /var/log/pixiv_crawler.log"
