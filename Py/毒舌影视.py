# -*- coding: utf-8 -*-
# 毒舌影视（dushe7.app）TVBox Python 源  type=3
#
# 站点形态（2026-11-07 实测）：
#   - 非 MacCMS：/api.php/provide/vod/、/index.php/ajax/data 均 404（openresty）
#   - 纯 PC 模板网页站，路由为：
#       频道   /channel/{tid}.html            1电影 2连续剧 3动漫 4综艺纪录 6短剧
#       分类   /show/{tid}------{pg}.html     每页 18 条，只有“下一页”
#       详情   /detail/{vod}.html
#       播放   /play/{vod}-{线路}-{episode}.html
#       搜索   /search?k={关键词}&t={token}[&page=N]
#   - 反爬：所有页面先返回 850 + "Protected by cdndefend" 的 JS 校验页，
#     需算出 sha1 前若干字节满足条件的 i，写入 cdndefend_js_cookie={常量+i} 后重试；
#     cookie 失效会再次下发校验页，本文件遇到即重新计算。
#   - 详情页播放地址不在详情页，而在每条线路的播放页里：
#       const playSource = { src: "https://.../index.m3u8?appId=dsdy&sign=...&timestamp=...", ... }
#     src 带 sign/timestamp 时效签名（timestamp 为签发时间），因此必须“播放时现取”，
#     不能把取流地址写进 vod_play_url 缓存。
#   - m3u8 实测可直接 GET（无需 Referer、无需 Cookie，证书对 IP 有效），但部分线路
#     （如“4K”）站点自身 src 为空，这类线路在播放时按同一集号回退到其它线路取流（最多试 3 条）。
#
# 约定：
#   - 搜索优先走站点原生 /search，再用本地规则严格过滤（片名/演员/导演，不拆词、不搜简介）；
#     站点原生搜索是模糊的（搜“不存在的片子zzz”也返回 18 条），必须过滤。
#   - 首页分类优先从导航解析，解析失败回落内置表；分类/搜索任何单页失败只返回空列表，不抛异常。

import hashlib
import html as html_mod
import re
import threading
import time
from urllib.parse import unquote, urlencode, urljoin, urlsplit

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


BASE = "https://www.dushe7.app"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

DEFAULT_CLASSES = [
    ("1", "电影"),
    ("2", "连续剧"),
    ("3", "动漫"),
    ("4", "综艺纪录"),
    ("6", "短剧"),
]

# cdndefend 校验页特征
CH_MARK = "cdndefend"
CH_ARRAY = re.compile(r"a0_0x2a54=\[(.*?)\];", re.S)
CH_ROT = re.compile(r"\(a0_0x2a54,\s*(0x[0-9a-fA-F]+)\)")
CH_NEED = re.compile(
    r"s\[n1\]\s*===\s*0x([0-9a-fA-F]+)\s*&&\s*s\[n1\+0x1\]\s*===\s*0x([0-9a-fA-F]+)"
)

_LOCK = threading.Lock()


def _text(s, keep_lines=False):
    s = str(s or "")
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    if keep_lines:
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        return re.sub(r"\n{3,}", "\n\n", s).strip()
    return re.sub(r"\s+", " ", s).strip()


def _abs(href):
    href = str(href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    return urljoin(BASE + "/", href)


# 站点标题把分卷后缀直接连在片名后面（"持械入宋第一季"），标题原样保留、不做改写；
# 只把分卷后缀追加到 vod_remarks 角标右端（"更新第100集｜第一季"），便于分卷辨识。
# 覆盖常见分卷用字：季/篇/章/部/卷（中文数字与阿拉伯数字）。
# 刻意不覆盖「集」：集是单集单位，角标本身就有「更新第N集」，再拼一次只会重复且易混淆。
_NUM = r"[0-9零〇一二三四五六七八九十百千两]+"
SEASON_UNIT = r"[季篇章部卷]"
SEASON_ONLY = re.compile(r"^第?\s*%s\s*%s$" % (_NUM, SEASON_UNIT))
SEASON_TAIL = re.compile(
    r"^(.+?)[\s·:：\-]*第\s*(%s)\s*(%s)$" % (_NUM, SEASON_UNIT))


def _split_season(name):
    """从标题末尾识别分卷后缀，返回 (片名前缀, 后缀)；识别不到时后缀为 ""。

    只认「整条标题以第X季/篇/章/部/卷结尾、且前面还有片名」的情况：
      - "持械入宋第一季"                    -> ("持械入宋", "第一季")
      - "聚宝仙盆之杂灵根才是真BOSS第十五季" -> ("聚宝仙盆之杂灵根才是真BOSS", "第十五季")
      - "某某传第二部" / "某剧第100卷"       -> ("某某传", "第二部") / ("某剧", "第100卷")
      - "第2季"（本身就只有后缀）            -> ("第2季", "")
      - "十八岁太奶奶驾到重整家族荣耀5"       -> 原样返回，后缀为 ""
      - "某剧第一季 特别篇"（后缀不在结尾）   -> 原样返回，后缀为 ""
    片名本身就以「第X季」结尾（例如正片名就叫"某剧第二季"）时，仍会被识别出来，
    但标题不改写，后缀只是多写进角标一次，不影响名称显示。
    """
    name = str(name or "").strip()
    m = SEASON_TAIL.match(name)
    if not m:
        return name, ""
    base = m.group(1).strip()
    if not base or SEASON_ONLY.match(base):
        return name, ""
    return base, "第%s%s" % (m.group(2), m.group(3))


def _remark_with_season(remark, season):
    remark = str(remark or "").strip()
    if not season:
        return remark
    return "%s｜%s" % (remark, season) if remark else season


# 说明：站点封面同样走 cdndefend 校验（直接 GET 返回 850），TVBox 的图片加载器
# 无法携带本文件算出的 cookie，返回封面地址只会破图，故列表/详情统一留空，
# 由 App 显示自身占位图。


class Spider(BaseSpider):

    def getName(self):
        return "毒舌影视"

    def init(self, extend=""):
        self.extend = extend or ""
        self._sess = requests.Session()
        self._sess.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._token = ("", 0.0)
        self._classes = None
        return {}

    def destroy(self):
        try:
            self._sess.close()
        except Exception:
            pass
        return {}

    # ------------------------------------------------------------------
    # 网络层：cdndefend 校验 + 超时重试
    # ------------------------------------------------------------------
    def _solve_challenge(self, html):
        """返回 (cookie名, cookie值)；算法：sha1(常量 + i) 的指定字节命中即写 cookie。"""
        m = CH_ARRAY.search(html)
        if not m:
            return None
        arr = re.findall(r"'([^']*)'", m.group(1))
        if not arr:
            return None

        rot = CH_ROT.search(html)
        if rot:
            try:
                for _ in range(int(rot.group(1), 16) % len(arr)):
                    arr.append(arr.pop(0))
            except Exception:
                pass

        cookie_name = "cdndefend_js_cookie"
        for item in arr:
            if "cdndefend" in item:
                cookie_name = item.split("=")[0].strip() or cookie_name
                break

        token = ""
        for item in arr:
            if re.fullmatch(r"[0-9A-Fa-f]{24,64}", item):
                token = item
                break
        if not token:
            return None

        need = (0xB0, 0x0B)
        nm = CH_NEED.search(html)
        if nm:
            need = (int(nm.group(1), 16), int(nm.group(2), 16))

        idx = int(token[0], 16)  # parseInt('0x' + c[0])
        if idx + 1 >= 20:
            idx = 3

        for i in range(2000000):
            d = hashlib.sha1((token + str(i)).encode("utf-8")).digest()
            if d[idx] == need[0] and d[idx + 1] == need[1]:
                return cookie_name, token + str(i)
        return None

    def _get(self, url, referer=None, retries=2):
        """返回页面文本；失败返回 ''，不抛异常。"""
        if not getattr(self, "_sess", None):
            self.init()
        headers = {}
        if referer:
            headers["Referer"] = referer

        for _ in range(max(1, retries + 1)):
            try:
                with _LOCK:
                    r = self._sess.get(url, headers=headers, timeout=(6, 12),
                                       verify=False, allow_redirects=True)
                    text = r.text or ""
                    if CH_MARK in text and CH_ARRAY.search(text):
                        solved = self._solve_challenge(text)
                        if solved:
                            name, value = solved
                            host = urlsplit(url).hostname or "www.dushe7.app"
                            self._sess.cookies.set(name, value, domain=host, path="/")
                            r.close()
                            continue
                        return ""
                    if r.status_code >= 400:
                        return ""
                    return text
            except Exception:
                time.sleep(0.4)
        return ""

    # ------------------------------------------------------------------
    # 首页
    # ------------------------------------------------------------------
    def _nav_classes(self):
        if self._classes:
            return self._classes
        static = [{"type_id": t, "type_name": n} for t, n in DEFAULT_CLASSES]
        html = self._get(BASE + "/")
        found = []
        for m in re.finditer(
                r'href="/channel/(\d+)\.html"([\s\S]{0,300}?)menu-item-label">([^<]+)</div>',
                html):
            tid, name = m.group(1), _text(m.group(3))
            if name and all(c["type_id"] != tid for c in found):
                found.append({"type_id": tid, "type_name": name})
        self._classes = found if len(found) >= 3 else static
        return self._classes

    def homeContent(self, filter=False):
        try:
            return {"class": self._nav_classes(), "filters": {}, "list": []}
        except Exception:
            return {"class": [{"type_id": t, "type_name": n} for t, n in DEFAULT_CLASSES],
                    "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    # ------------------------------------------------------------------
    # 列表 / 搜索 / 详情 解析
    # ------------------------------------------------------------------
    def _list_item(self, block):
        # 只在卡片自身的 <a class="v-item"> 内取节点：频道页有多张卡片挤在同一个
        # module-item 里的情况，跨卡片取节点会把邻卡标题当成自己的名字。
        m = re.search(r'<a[^>]+href="/detail/(\d+)\.html"[^>]*>([\s\S]*?)</a>', block)
        if not m:
            return None

        vid, card = m.group(1), m.group(2)

        # 标题节点：前后两个是 display:none 水印，中间那个才是真标题；
        # 若出现纯季数节点则忽略，并取最长的一条（真标题一定比季数长）。
        titles = []
        for attrs, body in re.findall(r'<div class="v-item-title"([^>]*)>([\s\S]*?)</div>', card):
            if "display:none" in attrs.replace(" ", "").replace("\t", ""):
                continue
            t = _text(body)
            if t:
                titles.append(t)
        good = [t for t in titles if not SEASON_ONLY.match(t)]
        name = max(good or titles, key=len) if (good or titles) else ""
        _, season = _split_season(name)

        remark = ""
        rm = re.search(r'<div class="v-item-bottom">[\s\S]*?<span>([\s\S]*?)</span>', card)
        if rm:
            remark = _text(rm.group(1))
        remark = _remark_with_season(remark, season)

        if not name:
            return None

        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": "",
            "vod_remarks": remark,
        }

    def _parse_list(self, html):
        out = []
        seen = set()
        for block in re.split(r'(?=<div class="module-item">)', html):
            if 'class="module-item"' not in block:
                continue
            item = self._list_item(block)
            if item and item["vod_id"] not in seen:
                seen.add(item["vod_id"])
                out.append(item)
        return out

    def _has_next(self, html):
        return "page-item-next" in html and "下一页" in html

    # ------------------------------------------------------------------
    # 分类
    # ------------------------------------------------------------------
    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        tid = str(tid or "").strip()
        try:
            pn = max(1, int(str(pg)))
        except Exception:
            pn = 1

        if not tid:
            return {"list": [], "page": pn, "pagecount": pn, "limit": 18, "total": 0}

        html = self._get("%s/show/%s------%d.html" % (BASE, tid, pn))
        items = self._parse_list(html)

        # 第 1 页失败时退回频道页（48 条首页聚合，无分页）
        if not items and pn == 1:
            html = self._get("%s/channel/%s.html" % (BASE, tid))
            items = self._parse_list(html)

        pagecount = pn + 1 if (items and self._has_next(html)) else pn
        return {
            "list": items,
            "page": pn,
            "pagecount": pagecount,
            "limit": len(items) or 18,
            "total": len(items),
        }

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------
    def _search_token(self, force=False):
        token, expire = self._token
        if token and not force and expire > time.time():
            return token
        html = self._get(BASE + "/")
        m = re.search(r'/search\?k=[^"&]+&(?:amp;)?t=([^"&]+)', html)
        token = unquote(m.group(1)) if m else ""
        if token:
            self._token = (token, time.time() + 300)
        return token

    @staticmethod
    def _kw_hit(key, *fields):
        kw = re.sub(r"\s+", "", str(key or "")).lower()
        if not kw:
            return True
        for f in fields:
            if kw in re.sub(r"\s+", "", str(f or "")).lower():
                return True
        return False

    def _parse_search(self, html):
        out = []
        seen = set()
        for block in re.split(r'(?=<a href="/detail/\d+\.html" class="search-result-item">)', html):
            m = re.search(r'href="/detail/(\d+)\.html"', block)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue

            t = re.search(r'<div class="title">([\s\S]*?)</div>', block)
            name = _text(t.group(1)) if t else ""
            # 标题异常（空或只有一个季数）时退回封面 alt/title，那里也是完整标题
            if not name or SEASON_ONLY.match(name):
                alt = re.search(r'<img[^>]+(?:alt|title)="([^"]+)"', block)
                cand = _text(alt.group(1)) if alt else ""
                if cand and "kekys" not in cand.lower() and not SEASON_ONLY.match(cand):
                    name = cand
            _, season = _split_season(name)
            if not name:
                continue

            tag_box = re.search(r'<div class="tags">([\s\S]*?)</div>', block)
            tags = [_text(x) for x in re.findall(r"<span>([\s\S]*?)</span>",
                                                 tag_box.group(1) if tag_box else "")]
            actors = ""
            ac = re.search(r'<div class="actors">([\s\S]*?)</div>', block)
            if ac:
                actors = _text(ac.group(1))

            year = ""
            for tag in tags:
                if re.fullmatch(r"\d{4}", tag):
                    year = tag
                    break

            area = ""
            rest = [x for x in tags if x and x != year and "/" not in x]
            if rest:
                area = rest[0]

            header = re.search(r'<div class="search-result-item-header">[\s\S]*?<div>([^<]+)</div>', block)
            type_name = _text(header.group(1)) if header else ""

            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": "",
                "vod_year": year,
                "vod_area": area,
                "vod_actor": actors,
                "type_name": type_name,
                "vod_remarks": season,
            })
        return out

    def searchContent(self, key, quick=False, pg=1):
        key = str(key or "").strip()
        if not key:
            return {"list": []}
        try:
            pn = max(1, int(str(pg)))
        except Exception:
            pn = 1

        def query(token):
            params = {"k": key, "t": token}
            if pn > 1:
                params["page"] = pn
            return self._get(BASE + "/search?" + urlencode(params))

        html = query(self._search_token())
        if "search-result-item" not in html:
            html = query(self._search_token(force=True))

        native = self._parse_search(html)

        # 站点搜索是模糊匹配（会按简介/拆词召回），这里只认片名/演员/导演的完整子串
        items = [v for v in native
                 if self._kw_hit(key, v.get("vod_name"), v.get("vod_actor"), v.get("vod_director"))]

        return {
            "list": items,
            "page": pn,
            "pagecount": pn + 1 if (items and self._has_next(html)) else pn,
            "limit": len(items) or 18,
            "total": len(items),
        }

    # ------------------------------------------------------------------
    # 详情
    # ------------------------------------------------------------------
    def _parse_detail(self, html, vid):
        title_block = re.search(r'<div class="detail-title">([\s\S]*?)</div>', html)
        name = ""
        if title_block:
            strongs = [_text(x) for x in re.findall(r"<strong>([\s\S]*?)</strong>", title_block.group(1))]
            # 模板用 CSS 隐藏奇数位 strong，真名在偶数位（1 基）
            name = "".join(strongs[1::2]).strip()
            if not name:
                name = "".join(x for x in strongs if "kekys" not in x.lower()).strip()

        if not name:
            t = re.search(r"<title>([\s\S]*?)</title>", html)
            name = _text(t.group(1)).split("-")[0].strip() if t else ""

        _, season = _split_season(name)

        tags = [_text(x) for x in re.findall(r'class="detail-tags-item">([\s\S]*?)</a>', html)]
        year = ""
        for tag in tags:
            if re.fullmatch(r"\d{4}", tag):
                year = tag
                break
        rest = [x for x in tags if x and x != year]
        area = rest[0] if rest else ""
        genre = ",".join(rest[1:]) if len(rest) > 1 else ""

        info = {}
        for side, main in re.findall(
                r'detail-info-row-side">([\s\S]{0,20}?)</div>\s*'
                r'<div class="detail-info-row-main">([\s\S]*?)</div>', html):
            label = _text(side).rstrip(":：")
            if label and label not in info:
                info[label] = _text(main)

        desc = ""
        dm = re.search(r'<div class="detail-desc">([\s\S]*?)</div>', html)
        if dm:
            desc = _text(dm.group(1), keep_lines=True)

        # 线路与选集：source-item 与 episode-list 一一对应（均为 18 条）
        labels = [_text(x) for x in re.findall(
            r'class="source-item[^"]*"[^>]*>[\s\S]*?source-item-label">([\s\S]*?)</span>', html)]

        blocks = re.findall(r'<div class="episode-list"[^>]*>([\s\S]*?)</div>', html)

        froms = []
        urls = []
        for i, block in enumerate(blocks):
            episodes = re.findall(
                r'<a href="(/play/[^"]+\.html)"[^>]*>\s*<span>([\s\S]*?)</span>', block)
            if not episodes:
                continue
            line = labels[i] if i < len(labels) and labels[i] else ("线路%d" % (i + 1))
            froms.append(line.replace("$", "").replace("#", ""))
            urls.append("#".join(
                "%s$%s" % (_text(ep).replace("$", "").replace("#", ""), _abs(href))
                for href, ep in episodes))

        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": "",
            "type_name": genre or (rest[-1] if rest else ""),
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": _remark_with_season(info.get("备注", ""), season),
            "vod_actor": info.get("演员", ""),
            "vod_director": info.get("导演", ""),
            "vod_content": desc,
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) and ids else ids
        vid = str(vid or "").strip()
        m = re.search(r"(\d+)", vid)
        if not m:
            return {"list": []}
        vid = m.group(1)

        html = self._get("%s/detail/%s.html" % (BASE, vid))
        if not html or 'class="detail-title"' not in html:
            return {"list": []}

        try:
            vod = self._parse_detail(html, vid)
        except Exception:
            return {"list": []}

        if not vod.get("vod_name"):
            return {"list": []}
        return {"list": [vod]}

    # ------------------------------------------------------------------
    # 播放
    # ------------------------------------------------------------------
    def _play_page(self, url):
        m = re.search(r"/play/(\d+)-\d+-\d+\.html", url)
        vod = m.group(1) if m else ""
        referer = ("%s/detail/%s.html" % (BASE, vod)) if vod else (BASE + "/")
        return self._get(url, referer=referer)

    @staticmethod
    def _play_src(html):
        if not html:
            return ""
        block = re.search(r"playSource\s*=\s*\{([\s\S]*?)\}\s*;", html)
        src = ""
        if block:
            m = re.search(r'src\s*:\s*["\']([^"\']*)["\']', block.group(1))
            src = m.group(1) if m else ""
        if not src:
            m = re.search(r'src\s*:\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']', html)
            src = m.group(1) if m else ""
        src = src.replace("\\/", "/").strip()
        return _abs(src) if src else ""

    def _play_fallback(self, url, html):
        """站点部分线路 src 为空（实测“4K”线路），按同一集号换线路再取，最多 3 条。"""
        vm = re.search(r"/play/(\d+)-(\d+)-(\d+)\.html", url)
        if not vm:
            return ""
        vod = vm.group(1)
        im = re.search(r"episodeIndex\s*:\s*(\d+)", html or "")
        if not im:
            return ""
        index = int(im.group(1))
        if index < 1:
            return ""

        detail = self._get("%s/detail/%s.html" % (BASE, vod))
        if not detail:
            return ""

        tried = 1
        for block in re.findall(r'<div class="episode-list"[^>]*>([\s\S]*?)</div>', detail):
            cand = re.search(r'<a href="(/play/[^"]+)"[^>]*data-index="%d"' % index, block)
            if not cand:
                continue
            page = cand.group(1)
            if page in url:
                continue
            src = self._play_src(self._play_page(_abs(page)))
            if src:
                return src
            tried += 1
            if tried > 3:
                break
        return ""

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "").strip()
        if raw.startswith("http"):
            url = raw
        elif raw.startswith("/"):
            url = BASE + raw
        else:
            url = "%s/play/%s.html" % (BASE, raw)

        html = self._play_page(url)
        src = self._play_src(html)
        if not src:
            src = self._play_fallback(url, html)

        return {
            "parse": 0,
            "playUrl": "",
            "url": src,
            "header": {"User-Agent": UA, "Referer": BASE + "/"},
        }

    # ------------------------------------------------------------------
    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(x in u for x in (".m3u8", ".mp4", ".flv", ".ts"))

    def manualVideoCheck(self):
        return False
