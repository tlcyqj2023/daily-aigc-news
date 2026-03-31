import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests


GDELT_DOC_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
WXPUSHER_SEND_ENDPOINT = "https://wxpusher.zjiecode.com/api/send/message"


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    domain: str | None
    seen_date: str | None
    source_country: str | None


def fetch_hacker_news_aigc(*, hours: int = 24) -> list[Article]:
    # Hacker News Algolia API
    # 抓取最近 N 小时内的 AI 相关高赞文章
    import time
    from urllib.parse import urlparse
    
    now_ts = int(time.time())
    start_ts = now_ts - (hours * 3600)
    
    # 搜索标题包含 AI/LLM/GPT/OpenAI 等关键词的 story
    # 修改 query 为 Hacker News Algolia 支持的格式，不要用 OR 而是用逗号或空格，这里直接用简单关键词
    query = "AI"
    url = "https://hn.algolia.com/api/v1/search_by_date"
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"created_at_i>{start_ts}",
        "hitsPerPage": 30,
    }
    
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    
    hits = data.get("hits") or []
    
    seen_urls: set[str] = set()
    articles: list[Article] = []
    
    for item in hits:
        item_url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        
        # HN 有些是内部讨论帖没有外链，用 HN 链接替代
        if not item_url:
            item_id = item.get("objectID")
            if item_id:
                item_url = f"https://news.ycombinator.com/item?id={item_id}"
            else:
                continue
                
        if not title:
            continue
            
        if item_url in seen_urls:
            continue
        seen_urls.add(item_url)
        
        domain = None
        try:
            domain = urlparse(item_url).netloc
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            pass
            
        created_at = item.get("created_at") or ""
        
        articles.append(
            Article(
                title=title,
                url=item_url,
                domain=domain,
                seen_date=created_at[:10] if created_at else None, # 只取日期部分 YYYY-MM-DD
                source_country="Hacker News",
            )
        )
        
    return articles


def fetch_aigc_articles(*, hours: int = 24, max_records: int = 50) -> list[Article]:
    query = (
        '(AIGC OR "generative AI" OR "foundation model" OR "large language model" OR '
        "LLM OR \"text-to-image\" OR \"diffusion model\" OR \"AI agent\")"
        " (technology OR research OR model OR release OR open-source OR regulation OR policy)"
    )

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(max_records),
        "sort": "HybridRel",
        "timespan": f"{hours}h",
    }

    resp = requests.get(
        GDELT_DOC_ENDPOINT,
        params=params,
        headers={"User-Agent": "ai-news-bot/1.0"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    articles_raw = data.get("articles") or []

    seen_urls: set[str] = set()
    articles: list[Article] = []
    for item in articles_raw:
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not url or not title:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        articles.append(
            Article(
                title=title,
                url=url,
                domain=(item.get("domain") or None),
                seen_date=(item.get("seendate") or None),
                source_country=(item.get("sourceCountry") or None),
            )
        )

    return articles


def translate_text(text: str) -> str:
    """使用免费的 Google Translate 接口将文本翻译为中文"""
    if not text:
        return text
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        translated = "".join([sentence[0] for sentence in data[0] if sentence[0]])
        return translated
    except Exception as e:
        print(f"Translation failed for '{text}': {e}")
        return text  # 翻译失败时返回原英文


def format_markdown(articles: list[Article], *, hours: int) -> str:
    now_local = datetime.now().astimezone()
    
    # 顶部横幅设计：使用表情、加粗和引用块营造层级感
    header = (
        f"## 🤖 AIGC 科技前沿速递\n\n"
        f"> **聚合过去 {hours} 小时全网最有价值的 AI 资讯**\n"
        f"> 🗓️ 更新时间：`{now_local:%Y-%m-%d %H:%M}`\n\n"
        f"---\n\n"
    )

    if not articles:
        return header + "📭 **当前时段未抓取到高权重资讯，请稍后再试。**\n\n*（可能原因：接口临时波动或时段内无重大新闻）*"

    lines: list[str] = [header]
    
    # 定义不同序号的专属图标，提升视觉体验
    def get_rank_icon(index: int) -> str:
        if index == 1: return "🥇"
        if index == 2: return "🥈"
        if index == 3: return "🥉"
        return "🔹"

    for idx, a in enumerate(articles[:10], start=1):
        cn_title = translate_text(a.title)
        source = a.source_country or a.domain or "Global Media"
        date_str = a.seen_date or datetime.now().astimezone().strftime("%Y-%m-%d")
        
        # 截断过长的域名/来源，保持排版整洁
        if len(source) > 20:
            source = source[:17] + "..."
            
        icon = get_rank_icon(idx)
        
        # 资讯卡片式排版：
        # 标题行加粗，并附带序号图标和链接
        # 元数据行使用小字/代码块体呈现，增强专业感
        article_block = (
            f"### {icon} [{cn_title}]({a.url})\n"
            f"🗞️ `来源: {source}` ⏳ `时间: {date_str}`\n"
        )
        lines.append(article_block)
        
    # 底部页脚
    footer = (
        f"\n---\n"
        f"💡 *此报表由 GitHub Actions 自动化引擎生成*\n"
        f"🔗 *Powered by GDELT & Hacker News*"
    )
    lines.append(footer)
    
    return "\n".join(lines).strip()


def send_to_wechat_via_wxpusher(*, app_token: str, uids: list[str], markdown: str) -> dict:
    payload = {
        "appToken": app_token,
        "content": markdown,
        "contentType": 3,
        "uids": uids,
        "summary": "AIGC 资讯",
    }
    resp = requests.post(WXPUSHER_SEND_ENDPOINT, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("success") is False:
        code = data.get("code")
        msg = data.get("msg")
        raise RuntimeError(f"WxPusher send failed (code={code}, msg={msg})")
    return data


def fetch_with_retry_and_fallback(*, hours: int = 24, max_records: int = 50) -> tuple[list[Article], list[str]]:
    # 数据源抓取顺序
    fetchers = [
        ("GDELT", lambda: fetch_aigc_articles(hours=hours, max_records=max_records)),
        ("Hacker News", lambda: fetch_hacker_news_aigc(hours=hours)),
    ]
    
    max_retries = 3
    retry_delay = 180  # 3 分钟
    
    errors: list[str] = []
    
    for attempt in range(max_retries):
        for source_name, fetcher in fetchers:
            try:
                print(f"[Attempt {attempt+1}/{max_retries}] Fetching from {source_name}...")
                articles = fetcher()
                if articles:
                    return articles, errors
                else:
                    errors.append(f"[Attempt {attempt+1}] {source_name} returned empty list.")
            except Exception as e:
                err_msg = f"[Attempt {attempt+1}] {source_name} error: {type(e).__name__}: {e}"
                print(err_msg)
                errors.append(err_msg)
        
        # 如果当前回合所有数据源都失败/为空，且还没到最后一次重试，则等待 3 分钟
        if attempt < max_retries - 1:
            print(f"All sources failed or returned empty. Waiting {retry_delay} seconds before next attempt...")
            time.sleep(retry_delay)
            
    # 连续 3 次全部失败，返回空列表和收集到的所有错误
    return [], errors


def main() -> None:
    app_token = (os.environ.get("WXPUSHER_APP_TOKEN") or os.environ.get("APP_TOKEN") or "").strip()
    uid = (os.environ.get("WXPUSHER_UID") or os.environ.get("UID") or "").strip()
    uids_raw = os.environ.get("WXPUSHER_UIDS") or ""
    hours = int(os.environ.get("LOOKBACK_HOURS") or "24")
    dry_run = (os.environ.get("DRY_RUN") or "").strip() == "1"

    if not app_token:
        raise SystemExit(
            "Missing WXPUSHER_APP_TOKEN (or APP_TOKEN) env var (set GitHub Actions secret)."
        )

    uids = [u.strip() for u in uids_raw.split(",") if u.strip()] if uids_raw else ([uid] if uid else [])
    if not uids:
        raise SystemExit(
            "Missing WXPUSHER_UID/WXPUSHER_UIDS (or UID) env var (set GitHub Actions secret)."
        )

    try:
        articles, errors = fetch_with_retry_and_fallback(hours=hours, max_records=50)
        
        if articles:
            markdown = format_markdown(articles, hours=hours)
        else:
            now_local = datetime.now().astimezone()
            error_details = "\n\n".join(errors[-6:]) # 只展示最后两轮的错误，避免超长
            markdown = (
                f"近{hours}小时 AIGC 科技资讯（抓取失败）\n\n"
                f"更新时间：{now_local:%Y-%m-%d %H:%M:%S %Z}\n\n"
                f"**已连续 3 次尝试所有备用数据源，均告失败。错误日志如下：**\n\n"
                f"```text\n{error_details}\n```"
            )
            
    except Exception as e:
        now_local = datetime.now().astimezone()
        markdown = (
            f"近{hours}小时 AIGC 科技资讯（系统崩溃）\n\n更新时间：{now_local:%Y-%m-%d %H:%M:%S %Z}\n\n"
            f"未捕获的系统错误：{type(e).__name__}: {e}"
        )
    print(markdown)
    if dry_run:
        return

    try:
        result = send_to_wechat_via_wxpusher(app_token=app_token, uids=uids, markdown=markdown)
        print(result)
    except Exception as e:
        raise SystemExit(f"{type(e).__name__}: {e}") from e


if __name__ == "__main__":
    main()
