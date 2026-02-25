from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from scripts.aigc_news_push import (
    Article,
    fetch_aigc_articles,
    format_markdown,
    send_to_wechat_via_wxpusher,
)


def test_format_markdown_empty() -> None:
    md = format_markdown([], hours=24)
    assert "近24小时 AIGC 科技资讯" in md
    assert "未抓到匹配资讯" in md


def test_format_markdown_two_articles() -> None:
    articles = [
        Article(
            title="A",
            url="https://example.com/a",
            domain="example.com",
            seen_date="2026-01-01 00:00:00",
            source_country="US",
        ),
        Article(
            title="B",
            url="https://example.com/b",
            domain=None,
            seen_date=None,
            source_country=None,
        ),
    ]
    md = format_markdown(articles, hours=24)
    assert "1. [A](https://example.com/a)" in md
    assert "2. [B](https://example.com/b)" in md


def test_fetch_dedup_and_filter() -> None:
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json = Mock(
        return_value={
            "articles": [
                {"title": "T1", "url": "https://a.com/1", "domain": "a.com"},
                {"title": "T1-dup", "url": "https://a.com/1", "domain": "a.com"},
                {"title": "", "url": "https://a.com/2"},
                {"title": "T3", "url": ""},
                {"title": "T4", "url": "https://a.com/4", "sourceCountry": "US"},
            ]
        }
    )

    with patch("scripts.aigc_news_push.requests.get", return_value=mock_resp) as get:
        articles = fetch_aigc_articles(hours=24, max_records=50)
        assert [a.url for a in articles] == ["https://a.com/1", "https://a.com/4"]
        get.assert_called_once()


def test_send_payload_markdown() -> None:
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json = Mock(return_value={"success": True})

    with patch("scripts.aigc_news_push.requests.post", return_value=mock_resp) as post:
        result = send_to_wechat_via_wxpusher(
            app_token="AT_test",
            uids=["WX_x"],
            markdown="hello",
        )
        assert result == {"success": True}
        assert post.call_count == 1
        payload = post.call_args.kwargs["json"]
        assert payload["appToken"] == "AT_test"
        assert payload["uids"] == ["WX_x"]
        assert payload["contentType"] == 3


def test_send_raises_on_wxpusher_failure() -> None:
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json = Mock(return_value={"success": False, "code": 1001, "msg": "uid和topicId不能同时为空"})

    with patch("scripts.aigc_news_push.requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError) as e:
            send_to_wechat_via_wxpusher(app_token="AT_test", uids=[], markdown="hello")
        assert "code=1001" in str(e.value)


@pytest.mark.parametrize("hours", [1, 24, 72])
def test_fetch_timespan_hours(hours: int) -> None:
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json = Mock(return_value={"articles": []})

    with patch("scripts.aigc_news_push.requests.get", return_value=mock_resp) as get:
        fetch_aigc_articles(hours=hours, max_records=1)
        params = get.call_args.kwargs["params"]
        assert params["timespan"] == f"{hours}h"
