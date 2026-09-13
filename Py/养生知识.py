# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   养生知识 (Yst)

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

YEARS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"]
LIST_ID = "btv_08da67cea600bf3c78973427bfaba12d_s0_"
INFO = "https://pc.api.btime.com/btimeweb/infoFlow"
PLAY = "https://app.api.btime.com/video/play?callback=jQuery1&id="
ITEM = "https://item.btime.com/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "Referer": "https://www.btime.com/",
}
JP_RE = re.compile(r"^[^(]+\((.*)\)\s*;?\s*$", re.DOTALL)
TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.IGNORECASE)
IMG_RE = re.compile(r'(?:property="og:image"\s+content="([^"]+)"|video_covers"\s*:\s*"([^"]+))', re.IGNORECASE)


def _fix(u):
    return (u or "").replace("\\/", "/").strip()


def _list_id(i):
    return f"{LIST_ID}{YEARS[i]}"


class Spider(Spider):
    def getName(self):
        return "养生知识"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            return requests.get(url, headers=HEADERS, timeout=12).text
        except Exception:
            return ""

    def _item_to_vod(self, it):
        url = _fix(it.get("url") or "")
        if not url:
            gid = it.get("gid") or ""
            if not gid:
                return None
            url = ITEM + gid
        d = it.get("data") or {}
        title = (d or it).get("title") or url
        pic = ""
        if d:
            covers = d.get("covers") or []
            if covers:
                pic = _fix(str(covers[0]))
        dur = d.get("duration") or ""
        return {"vod_id": url, "vod_name": str(title), "vod_pic": pic, "vod_remarks": str(dur)}

    def _info_flow(self, list_id, pg):
        url = f"{INFO}?list_id={quote(list_id)}&refresh={quote(str(pg))}&count=20&expands=pageinfo"
        try:
            j = json.loads(self._get(url))
            lst = (j.get("data") or {}).get("list") or []
        except Exception:
            lst = []
        out = []
        for it in lst:
            v = self._item_to_vod(it)
            if v:
                out.append(v)
        return out

    def homeContent(self, filter):
        return {"class": [{"type_id": _list_id(i), "type_name": y} for i, y in enumerate(YEARS)],
                "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent(_list_id(0), "1", False, {})

    def _resolve_tid(self, tid):
        s = (tid or "").strip()
        if not s:
            return _list_id(0)
        if s.startswith("btv_"):
            return s
        m = re.match(r"^([23])-(\d+)(?:-H)?$", s)
        if m:
            i = int(m.group(2))
            if 0 <= i < len(YEARS):
                return _list_id(i)
        if s.isdigit():
            i = int(s)
            if 0 <= i < len(YEARS):
                return _list_id(i)
        for i, y in enumerate(YEARS):
            if s == y or s == _list_id(i) or _list_id(i).endswith("_s0_" + s):
                return _list_id(i)
        return _list_id(0)

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 9999}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            result["list"] = self._info_flow(self._resolve_tid(tid), pg)
            result["page"] = pg
            result["pagecount"] = pg + 1 if result["list"] else pg
        except Exception:
            pass
        return result

    @staticmethod
    def _streams(j):
        out = []
        try:
            d = j.get("data")
            arr = d.get("video_streams") if d else None
            if not arr:
                arr = d.get("audio_streams") if d else None
            def push(obj):
                if not isinstance(obj, dict):
                    return
                u = _fix(obj.get("stream_url") or "")
                if not u:
                    return
                name = obj.get("stream_vbt") or obj.get("duration") or "正片"
                out.append(f"{name}${u}")
            for it in arr or []:
                if isinstance(it, list):
                    for sub in it:
                        push(sub)
                else:
                    push(it)
        except Exception:
            pass
        return out

    def detailContent(self, ids):
        vod = {}
        try:
            raw = str(ids[0])
            sid = raw.strip()
            if "item.btime.com/" in sid:
                sid = sid[sid.index("item.btime.com/") + len("item.btime.com/"):]
            sid = re.sub(r"[?#].*", "", sid)
            if not raw.startswith("http"):
                raw = ITEM + sid
            html = self._get(raw)
            play_raw = self._get(PLAY + sid)
            m = JP_RE.match((play_raw or "").strip())
            if m:
                play_raw = m.group(1)
            title = ""
            m = TITLE_RE.search(html or "")
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()
                for sep in ("-", "_"):
                    idx = title.find(sep)
                    if idx > 0:
                        title = title[:idx].strip()
            title = title or "养生堂"
            pic = ""
            m = IMG_RE.search(html or "")
            if m:
                pic = _fix(m.group(1) or m.group(2))
            content = ""
            try:
                j = json.loads(play_raw or "")
                content = ((j.get("data") or {}).get("summary")) or ""
            except Exception:
                pass
            try:
                j = json.loads(play_raw or "")
            except Exception:
                j = {}
            urls = self._streams(j)
            vod = {
                "vod_id": raw,
                "vod_name": title,
                "vod_pic": pic,
                "vod_content": content,
                "vod_play_from": "默认",
                "vod_play_url": "#".join(urls),
            }
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        url = _fix(playId or "")
        try:
            if "app.api.btime.com/video/play" in url:
                raw = self._get(url)
                m = JP_RE.match((raw or "").strip())
                if m:
                    raw = m.group(1)
                j = json.loads(raw or "")
                urls = self._streams(j)
                if urls:
                    url = urls[0].split("$", 1)[1]
        except Exception:
            pass
        hdrs = dict(HEADERS)
        hdrs["Referer"] = "https://www.btime.com/"
        return {"parse": 0, "url": url, "header": hdrs}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            try:
                pg = max(1, int(pg))
            except Exception:
                pg = 1
            seen, out = {}, []
            start = min(len(YEARS) - 1, (pg - 1) * 2)
            for yi in range(start, len(YEARS)):
                if len(out) >= 40:
                    break
                for page in range(1, 9):
                    if len(out) >= 40:
                        break
                    try:
                        j = json.loads(self._get(
                            f"{INFO}?list_id={quote(_list_id(yi))}&refresh={page}&count=20&expands=pageinfo"))
                        lst = (j.get("data") or {}).get("list") or []
                    except Exception:
                        lst = []
                    for it in lst:
                        if len(out) >= 40:
                            break
                        d = it.get("data") or {}
                        title = (d or it).get("title") or ""
                        if not title or key not in str(title):
                            continue
                        v = self._item_to_vod(it)
                        if not v:
                            continue
                        k = it.get("url") or str(title)
                        if k in seen:
                            continue
                        seen[k] = 1
                        out.append(v)
            result["list"] = out
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
