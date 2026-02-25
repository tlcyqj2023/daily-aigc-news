import os
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


def format_markdown(articles: list[Article], *, hours: int) -> str:
    now_local = datetime.now().astimezone()
    header = f"近{hours}小时 AIGC 科技资讯（Top {min(10, len(articles))}）\n\n更新时间：{now_local:%Y-%m-%d %H:%M:%S %Z}\n\n"

    if not articles:
        return header + "未抓到匹配资讯（可能是接口临时波动或关键词过窄）。"

    lines: list[str] = [header]
    for idx, a in enumerate(articles[:10], start=1):
        meta_parts = [p for p in [a.domain, a.source_country, a.seen_date] if p]
        meta = " | ".join(meta_parts)
        if meta:
            lines.append(f"{idx}. [{a.title}]({a.url})\n   {meta}\n")
        else:
            lines.append(f"{idx}. [{a.title}]({a.url})\n")
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
        articles = fetch_aigc_articles(hours=hours, max_records=50)
        markdown = format_markdown(articles, hours=hours)
    except Exception as e:
        now_local = datetime.now().astimezone()
        markdown = (
            f"近{hours}小时 AIGC 科技资讯（抓取失败）\n\n更新时间：{now_local:%Y-%m-%d %H:%M:%S %Z}\n\n"
            f"错误：{type(e).__name__}: {e}"
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
