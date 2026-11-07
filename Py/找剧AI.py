# -*- coding: utf-8 -*-
# 找剧AI（zhaoju1.com）TVBox Python 源  type=3
#
# 站点形态（2026-11-07 实测）：
#   - 不是 CMS：/api.php/provide/vod/、/index.php/ajax/data 不存在，/ 只有 2KB 的 SPA 壳。
#   - 前端（React SPA）全部走同源 JSON 接口 /v1/...，且每个请求都要求 HMAC-SHA256 签名：
#       x-ai-movie-timestamp  = 毫秒时间戳
#       x-ai-movie-nonce      = 32 位随机 hex
#       x-ai-movie-signature  = HMAC_SHA256(secret, "METHOD\n{pathname}{search}\ntimestamp\nnonce")
#     密钥硬编码在 assets/movie-card-runtime-*.js 中（见下方 SIGN_KEY），无 cookie/登录要求。
#   - 数据接口：
#       首页     /v1/feed/home                       -> sections[].cards[]
#       分类     /v1/browse/catalog?kind=&page=&limit=   -> cards[] + pagination
#       搜索     /v1/browse/catalog?q=关键词&page=&limit= （与分类同一接口，原生搜索）
#       详情     /v1/catalog/{id}                    -> 元数据 + episodes[].token
#       取流     GET  /v1/playback/resolve/{episode_token}?view=compact  -> line_options[]
#                POST /v1/playback/resolve-line?view=compact {"ticket": ...} -> line.url
#   - 播放地址有两种：resolve_mode=direct 时 line_options[].url 就是 m3u8 直链；
#     resolve_mode=parse 时需要再 POST resolve-line 换出 mp4/m3u8。
#     实测部分直链域名已被封锁（返回“此網域已經遭到封鎖”），所以播放时按顺序挑
#     首个可用的 m3u8（优先）或 mp4，探测失败再换下一条；全部失败则回退首个候选，
#     避免在某个网络环境下因探测误判而完全无地址。
#   - 图片（poster_url，百度图床）可直连，无需签名。

import hashlib
import hmac
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlsplit

import requests

try:
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


BASE = "https://zhaoju1.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
SIGN_KEY = "8f18c8e472a9fefbab7108f5c447f69b48a4b5d34f662ed83163167fc10fb3b8"

CLASSES = [
    ("movie", "电影"),
    ("series", "剧集"),
    ("short_drama", "短剧"),
    ("anime", "动漫"),
    ("variety", "综艺"),
    ("documentary", "纪录片"),
    ("sports", "体育"),
]
KIND_NAME = dict(CLASSES)

_LOCK = threading.Lock()

# 一次播放最多检查的线路数 / 最多探测的 mp4 数，避免在弱网下等待过久
MAX_LINES = 8
MAX_MP4_PROBE = 2
# direct m3u8 并行探测：并发数 / 整体等待上限（秒）
PROBE_PARALLEL = 6
PROBE_WAIT = 7.0
# parse 线路需要逐条签名换地址，限制条数
MAX_PARSE_LINES = 3


class Spider(BaseSpider):

    def getName(self):
        return "找剧AI"

    def init(self, extend=""):
        self.extend = extend or ""
        self._sess = requests.Session()
        self._sess.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": BASE,
            "Referer": BASE + "/",
        })
        return {}

    def destroy(self):
        try:
            self._sess.close()
        except Exception:
            pass
        return {}

    # ------------------------------------------------------------------
    # 签名请求层
    # ------------------------------------------------------------------
    def _api(self, method, path, body=None, retries=2):
        """返回解析后的 dict；失败返回 {}。path 可含 query。"""
        if not getattr(self, "_sess", None):
            self.init()

        data = json.dumps(body) if body is not None else None
        for _ in range(max(1, retries + 1)):
            u = urlsplit(BASE + path)
            ts = str(int(time.time() * 1000))
            nonce = uuid.uuid4().hex
            query = ("?" + u.query) if u.query else ""
            msg = "%s\n%s%s\n%s\n%s" % (method, u.path, query, ts, nonce)
            sig = hmac.new(SIGN_KEY.encode("utf-8"), msg.encode("utf-8"),
                           hashlib.sha256).hexdigest()
            headers = {
                "x-ai-movie-timestamp": ts,
                "x-ai-movie-nonce": nonce,
                "x-ai-movie-signature": sig,
            }
            if data is not None:
                headers["Content-Type"] = "application/json"

            try:
                with _LOCK:
                    r = self._sess.request(method, BASE + path, headers=headers,
                                           data=data, timeout=(6, 15), verify=False)
                if r.status_code in (401, 403, 429, 500, 502, 503):
                    time.sleep(0.3)
                    continue
                if r.status_code >= 400:
                    return {}
                text = r.text or ""
                try:
                    return json.loads(text)
                except Exception:
                    return {}
            except Exception:
                time.sleep(0.3)
        return {}

    @staticmethod
    def _card_to_vod(c):
        if not isinstance(c, dict) or not c.get("id") or not c.get("title"):
            return None
        actors = [a for a in (c.get("actors") or []) if a]
        directors = [a for a in (c.get("directors") or []) if a]
        genres = [g for g in (c.get("genres") or []) if g]
        return {
            "vod_id": c.get("id"),
            "vod_name": c.get("title"),
            "vod_pic": c.get("poster_url") or c.get("carousel_url") or "",
            "vod_remarks": c.get("remarks") or "",
            "vod_year": str(c.get("year") or ""),
            "vod_area": c.get("area") or "",
            "vod_actor": ", ".join(actors),
            "vod_director": ", ".join(directors),
            "type_name": ", ".join(genres[:3]) or KIND_NAME.get(c.get("content_kind"), ""),
        }

    # ------------------------------------------------------------------
    # 首页
    # ------------------------------------------------------------------
    def homeContent(self, filter=False):
        return {
            "class": [{"type_id": t, "type_name": n} for t, n in CLASSES],
            "filters": {},
            "list": [],
        }

    def homeVideoContent(self):
        j = self._api("GET", "/v1/feed/home")
        out = []
        seen = set()
        for sec in j.get("sections") or []:
            for c in sec.get("cards") or []:
                vod = self._card_to_vod(c)
                if vod and vod["vod_id"] not in seen:
                    seen.add(vod["vod_id"])
                    out.append(vod)
        return {"list": out}

    # ------------------------------------------------------------------
    # 分类
    # ------------------------------------------------------------------
    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        tid = str(tid or "").strip()
        try:
            pn = max(1, int(str(pg)))
        except Exception:
            pn = 1

        if tid not in KIND_NAME:
            return {"list": [], "page": pn, "pagecount": pn, "limit": 20, "total": 0}

        j = self._api("GET", "/v1/browse/catalog?kind=%s&page=%d&limit=20" % (tid, pn))
        cards = j.get("cards") or []
        items = [v for v in (self._card_to_vod(c) for c in cards) if v]

        total = (j.get("pagination") or {}).get("total") or len(items)
        try:
            pagecount = max(pn, (int(total) + 19) // 20)
        except Exception:
            pagecount = pn

        return {
            "list": items,
            "page": pn,
            "pagecount": pagecount,
            "limit": len(items) or 20,
            "total": int(total) if str(total).isdigit() else len(items),
        }

    # ------------------------------------------------------------------
    # 搜索（站点原生 q 参数）
    # ------------------------------------------------------------------
    def searchContent(self, key, quick=False, pg=1):
        key = str(key or "").strip()
        if not key:
            return {"list": []}
        try:
            pn = max(1, int(str(pg)))
        except Exception:
            pn = 1

        path = "/v1/browse/catalog?q=%s&page=%d&limit=20" % (quote(key, safe=""), pn)
        j = self._api("GET", path)
        cards = j.get("cards") or []
        items = [v for v in (self._card_to_vod(c) for c in cards) if v]

        total = (j.get("pagination") or {}).get("total") or len(items)
        try:
            pagecount = max(pn, (int(total) + 19) // 20)
        except Exception:
            pagecount = pn

        return {
            "list": items,
            "page": pn,
            "pagecount": pagecount,
            "limit": len(items) or 20,
            "total": int(total) if str(total).isdigit() else len(items),
        }

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) and ids else ids
        vid = str(vid or "").strip()
        if not vid:
            return {"list": []}

        j = self._api("GET", "/v1/catalog/" + quote(vid, safe=""))
        if not j.get("title"):
            return {"list": []}

        episodes = j.get("episodes") or []
        names = []
        toks = []
        for idx, ep in enumerate(episodes):
            tok = ep.get("token") or ""
            if not tok:
                continue
            name = (ep.get("display_name") or ep.get("title")
                    or ("第%d集" % (idx + 1)))
            name = str(name).replace("$", "").replace("#", "")
            names.append("%s$%s" % (name, tok))
            toks.append(tok)

        actors = [a for a in (j.get("actors") or []) if a]
        directors = [a for a in (j.get("directors") or []) if a]
        genres = [g for g in (j.get("genres") or []) if g]

        vod = {
            "vod_id": vid,
            "vod_name": j.get("title"),
            "vod_pic": j.get("poster_url") or j.get("carousel_url") or "",
            "type_name": ", ".join(genres[:3]) or KIND_NAME.get(j.get("content_kind"), ""),
            "vod_year": str(j.get("year") or ""),
            "vod_area": j.get("area") or "",
            "vod_remarks": j.get("remarks") or j.get("episode_progress_text") or "",
            "vod_actor": ", ".join(actors),
            "vod_director": ", ".join(directors),
            "vod_content": j.get("description") or "",
            "vod_play_from": "默认线路" if names else "",
            "vod_play_url": "#".join(names),
        }
        return {"list": [vod]}

    # ------------------------------------------------------------------
    # 播放
    # ------------------------------------------------------------------
    @staticmethod
    def _probe(url, kind):
        """m3u8 取文本判断；mp4 用 Range 只拿头部。"""
        try:
            if kind == "m3u8":
                r = requests.get(url, timeout=(3, 5), verify=False,
                                 headers={"User-Agent": UA})
                return r.status_code == 200 and "#EXTM3U" in (r.text or "")[:2000]
            r = requests.get(url, timeout=(3, 5), verify=False, stream=True,
                             headers={"User-Agent": UA, "Range": "bytes=0-1023"})
            ok = r.status_code in (200, 206)
            r.close()
            return ok
        except Exception:
            return False

    def _resolve_line(self, ticket):
        j = self._api("POST", "/v1/playback/resolve-line?view=compact", {"ticket": ticket})
        line = j.get("line") or {}
        url = (line.get("url") or "").replace("\\/", "/").strip()
        kind = (line.get("url_kind") or "").lower()
        if not url.startswith("http"):
            return "", ""
        if kind not in ("m3u8", "mp4"):
            kind = "m3u8" if ".m3u8" in url.lower() else "mp4"
        return url, kind

    def _probe_first(self, urls, kind):
        """并行探测，按原顺序返回首个可用地址；全失败返回 ''。

        站点部分直链域名已被封锁，顺序探测会一直等到超时，这里并发探测、整体最多等
        PROBE_WAIT 秒，既缩短等待，又仍按线路优先级取舍。
        """
        urls = [u for u in urls if u][:PROBE_PARALLEL]
        if not urls:
            return ""
        if len(urls) == 1:
            return urls[0] if self._probe(urls[0], kind) else ""

        ok = {}
        ex = ThreadPoolExecutor(max_workers=min(PROBE_PARALLEL, len(urls)))
        try:
            futs = {ex.submit(self._probe, u, kind): i for i, u in enumerate(urls)}
            deadline = time.time() + PROBE_WAIT
            try:
                for f in as_completed(futs, timeout=max(0.2, deadline - time.time())):
                    try:
                        if f.result():
                            ok[futs[f]] = urls[futs[f]]
                    except Exception:
                        pass
            except Exception:
                pass
            if ok:
                return ok[min(ok)]
        finally:
            ex.shutdown(wait=False)
        return ""

    @staticmethod
    def _play(url):
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": UA, "Referer": BASE + "/"}}

    def playerContent(self, flag, id, vipFlags=None):
        token = str(id or "").strip()
        if not token:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}

        j = self._api("GET", "/v1/playback/resolve/" + quote(token, safe="") + "?view=compact")
        lines = j.get("line_options") or []

        direct_m3u8 = []
        direct_mp4 = []
        parse_tickets = []

        for ln in lines[:MAX_LINES]:
            url = (ln.get("url") or "").strip()
            kind = (ln.get("url_kind") or "").lower()
            mode = (ln.get("resolve_mode") or "").lower()

            if url.startswith("resolve://") or mode == "parse" or kind == "resolve_ticket":
                ticket = url[10:] if url.startswith("resolve://") else url
                if ticket:
                    parse_tickets.append(ticket)
                continue
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                continue
            if kind == "m3u8":
                direct_m3u8.append(url)
            else:
                direct_mp4.append(url)

        # 1) direct 线路的 m3u8：并发探测，首个可用即返回
        hit = self._probe_first(direct_m3u8, "m3u8")
        if hit:
            return self._play(hit)

        # 2) parse 线路：逐条换真实地址，再并发探测 m3u8
        parse_m3u8 = []
        parse_mp4 = []
        for ticket in parse_tickets[:MAX_PARSE_LINES]:
            url, kind = self._resolve_line(ticket)
            if not url:
                continue
            (parse_m3u8 if kind == "m3u8" else parse_mp4).append(url)
        hit = self._probe_first(parse_m3u8, "m3u8")
        if hit:
            return self._play(hit)

        # 3) mp4（direct + parse）：最多探测 MAX_MP4_PROBE 条
        mp4_all = (direct_mp4 + parse_mp4)[:MAX_MP4_PROBE]
        hit = self._probe_first(mp4_all, "mp4")
        if hit:
            return self._play(hit)

        # 探测全失败时仍返回候选，换网络环境可能可用
        fallback = (direct_m3u8 + parse_m3u8 + direct_mp4 + parse_mp4)
        return self._play(fallback[0] if fallback else "")

    # ------------------------------------------------------------------
    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(x in u for x in (".m3u8", ".mp4", ".flv", ".ts"))

    def manualVideoCheck(self):
        return False
