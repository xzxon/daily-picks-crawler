# 每日精选抓取器（Daily Picks Crawler）

多平台每日精选作品归档工具：从各平台的人气/热度排行榜建立候选池，过滤、评分、去重后每日精选一批作品下载归档，上传到自有存储并发送一条文字汇报。当前已实现 Pixiv 平台，后续平台按同样结构接入（抓取与选择模块按平台拆分，下载、上传、汇报流程复用）。

## 特性（Pixiv）

- 多榜单候选：日榜、周榜、原创榜、新人榜、月榜及 R-18 榜。
- 过滤漫画书/分镜：排除 manga、ugoira、多页、漫画标签、AI、低分辨率和异常比例作品。
- 综合评分：收藏数、收藏率、榜单排名、分辨率、新鲜度和来源权重。
- 作者每日去重；持久化作品 ID、原图 URL+页码和远端文件名去重。
- 文件名：`作者昵称_图片主题名_图片ID.后缀`。
- 普通与 R-18 分别上传到 `/Hermes/pixiv/` 和 `/Hermes/pixiv/R-18/`，上传后完整 GET SHA256 校验。
- 抓取、过滤、选择、下载、上传、校验均写入 JSONL 事件日志。
- QQ 仅发送一条文字汇报，不发送图片。

## 配置

复制 `.env.example` 为 `.env`，填入真实值；`.env` 禁止提交或打包（已在 `.gitignore` 中排除，`data/`、`downloads/`、日志文件同样不提交）。`config.yaml` 只保存非敏感策略参数。

```bash
cp .env.example .env
python3 -m pip install -r requirements.txt
python3 daily_run.py
```

可用参数：

```bash
python3 daily_run.py --skip-upload --skip-send
python3 crawler.py --config config.yaml
```

## 输出

默认输出目录由 `PIXIV_DAILY_OUTPUT_DIR` 指定，通常为 `/opt/data/projects/pixiv-daily-crawler/data/`。其中包含每日 `run_report_YYYY-MM-DD.json`、`new_items_YYYY-MM-DD.json`、`dedupe_state.json` 和 `events_YYYY-MM-DD.jsonl`。下载临时文件位于输出目录的 `downloads/`。

## 运行与安全边界

- 运行需要 Pixiv refresh token、OpenList WebDAV 凭据和可选 QQ 会话配置，全部从 `.env` 读取。
- R-18 内容只进入 R-18 目录；请遵守所在地法律和 Pixiv 使用规则。
- 旧 Top3/Top5 发送流程（`send_top3.py`）已废弃并从仓库移除，不会被新的 `daily_run.py` 调用；调试脚本 `_debug_s3.py` 同样已移除。
- `setup_cron.sh` 仅提供示例，不会自动修改系统 cron；现有 Nanobot 定时任务继续负责调度。
- 离线测试不得访问网络；真实运行前请先使用 `--skip-upload --skip-send` 检查下载结果。
