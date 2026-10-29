"""Offline filtering, scoring, quota selection and safe Pixiv filenames."""
from __future__ import annotations
import math, re, unicodedata
from datetime import date, datetime, timezone

DEFAULT_EXCLUDED_TAGS = {"manga", "comic", "comics", "storyboard", "ugoira", "漫画", "マンガ", "漫画形式", "四格", "4コマ", "分镜", "分鏡", "分鏡漫畫"}


def is_r18(item):
    return bool(item.get("is_r18")) or any(str(t).strip().lower() in {"r18", "r-18", "r-18g"} for t in item.get("tags", []))


def author(item):
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    return str(user.get("name") or user.get("account") or item.get("user_name") or item.get("author_name") or "unknown")


def dimensions(item):
    urls = item.get("original_urls") or []
    first = urls[0] if urls and isinstance(urls[0], dict) else {}
    try:
        return int(first.get("width") or item.get("width") or 0), int(first.get("height") or item.get("height") or 0)
    except (TypeError, ValueError):
        return 0, 0


def filter_reason(item, cfg):
    kind = str(item.get("type", "illust")).lower()
    if kind in {"manga", "ugoira"} or int(item.get("illust_type") or 0) in {1, 2}:
        return "manga_or_ugoira"
    if int(item.get("page_count") or 1) != 1:
        return "multi_page"
    tags = {str(t).strip().lower() for t in item.get("tags", [])}
    excluded = {str(x).strip().lower() for x in cfg.get("excluded_tags", DEFAULT_EXCLUDED_TAGS)}
    if tags & excluded:
        return "excluded_tag"
    if item.get("is_ai") or int(item.get("ai_type") or item.get("illust_ai_type") or 0) > 0:
        return "ai"
    created = str(item.get("create_date", ""))[:4]
    if created and created.isdigit() and int(created) < int(cfg.get("historical_min_year", 2020)):
        return "too_old"
    if int(item.get("total_bookmarks") or 0) < int(cfg.get("min_bookmarks", 0)):
        return "low_bookmarks"
    width, height = dimensions(item)
    if width < int(cfg.get("min_width", 1200)) or height < int(cfg.get("min_height", 1200)) or width * height < int(cfg.get("min_resolution", 2_000_000)):
        return "low_resolution"
    low, high = cfg.get("aspect_ratio", [0.45, 2.2])
    ratio = width / height if height else 0
    if not float(low) <= ratio <= float(high):
        return "abnormal_aspect_ratio"
    return None


def score(item, now=None):
    now = now or date.today()
    bookmarks = max(0, int(item.get("total_bookmarks") or 0))
    views = max(1, int(item.get("total_view") or item.get("view_count") or 1))
    rate = min(1.0, bookmarks / views * 12)
    rank = max(1, int(item.get("rank") or 100))
    rank_score = max(0.0, 1 - (rank - 1) / 100)
    width, height = dimensions(item)
    resolution = min(1.0, (width * height) / 8_000_000) if width and height else 0
    try:
        created = datetime.fromisoformat(str(item.get("create_date", "")).replace("Z", "+00:00"))
        if created.tzinfo:
            created = created.astimezone(timezone.utc).replace(tzinfo=None)
        age = max(0, (datetime.combine(now, datetime.min.time()) - created).days)
    except (TypeError, ValueError):
        age = 365
    freshness = max(0.0, 1 - age / 30)
    source = float(item.get("source_weight", 1.0) or 1.0)
    return round(math.log10(bookmarks + 1) * 30 + rate * 25 + rank_score * 20 + resolution * 10 + freshness * 10 + source * 5, 5)


def choose(items, cfg):
    accepted, filtered, seen = [], [], set()
    for raw in items:
        item = dict(raw)
        key = str(item.get("id", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        reason = filter_reason(item, cfg)
        if reason:
            item["filter_reason"] = reason
            filtered.append(item)
            continue
        item["score"] = score(item)
        item.setdefault("source_period", "recent")
        accepted.append(item)

    total = max(0, int(cfg.get("daily_total", 10)))
    target_normal = min(int(cfg.get("normal_quota", 7)), total)
    target_r18 = min(int(cfg.get("r18_quota", 3)), total - target_normal)
    period_targets = [("recent", min(int(cfg.get("recent_count", 6)), total)), ("historical", min(int(cfg.get("historical_count", 4)), total))]
    selected, used_ids, used_authors = [], set(), set()
    pool_limits = {False: target_normal, True: target_r18}

    def take(pool, limit=None, enforce_quota=True):
        nonlocal selected
        for item in sorted(pool, key=lambda x: (x["score"], str(x.get("id"))), reverse=True):
            if len(selected) >= total or (limit is not None and limit <= 0):
                break
            rid = str(item.get("id")); name = author(item); adult = is_r18(item)
            if rid in used_ids or name in used_authors:
                continue
            if enforce_quota and pool_limits[adult] <= 0:
                continue
            selected.append(item); used_ids.add(rid); used_authors.add(name)
            if enforce_quota:
                pool_limits[adult] -= 1
            if limit is not None:
                limit -= 1

    # Reserve the requested recent/history mix without exceeding normal/R-18 quotas.
    for period, limit in period_targets:
        take((x for x in accepted if x.get("source_period") == period), limit)
    # Fill any unfilled pool quotas from either period.
    take((x for x in accepted if not is_r18(x)))
    take((x for x in accepted if is_r18(x)))
    # If a pool is short, fill remaining slots from ordinary works first,
    # then R-18 only when the ordinary pool is exhausted.
    if len(selected) < total:
        take((x for x in accepted if not is_r18(x)), enforce_quota=False)
    if len(selected) < total:
        take((x for x in accepted if is_r18(x)), enforce_quota=False)
    return selected[:total], filtered


def safe_filename(item, used=None, max_len=180):
    used = used if used is not None else set()
    ext = str(item.get("extension") or ".jpg").lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"

    def clean(value):
        value = unicodedata.normalize("NFKC", str(value or "untitled"))
        value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", value)
        value = re.sub(r"\s+", "_", value)
        value = re.sub(r"[^\w\-。，、（）()\[\]]", "_", value, flags=re.UNICODE)
        return value.strip("._-") or "untitled"

    base = f"{clean(author(item))}_{clean(item.get('title'))}_{item.get('id', 'unknown')}"
    base = base[: max_len - len(ext)].rstrip("._-")
    name, index = base + ext, 2
    while name in used:
        suffix = f"_{index}"
        name = base[: max_len - len(ext) - len(suffix)] + suffix + ext
        index += 1
    used.add(name)
    return name


def image_key(item, page=0):
    urls = item.get("original_urls") or []
    url = urls[page].get("url") if page < len(urls) and isinstance(urls[page], dict) else item.get("image_url")
    return f"{url}#p{page}" if url else ""
