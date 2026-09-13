# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   最全短剧 (Kan90)
# 站点: https://20.90kan.cc (ext sites)
# 注意: 播放地址为夸克/百度分享链, 需账号 token 才能解析为直链;列表/搜索/详情完整可用,
#       详情页在播放列表以"分享链"呈现, 未识别到时备注提示.

from base.spider import Spider
import requests
import re
from urllib.parse import quote

SITE = "https://20.90kan.cc"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
RE_SHARE_BLOCK = re.compile(r"《([^》]+)》(?:[^》]*?)(https?://(?:pan\.quark\.cn|pan\.baidu\.com)/s/[a-zA-Z0-9]+)")
RE_SHARE_URL = re.compile(r"https?://(?:pan\.quark\.cn|pan\.baidu\.com)/[^\s\"'<>]+")


def _text(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _blocks(html):
    # 按 class="img-modbox" 切片提取
    out = []
    for m in re.finditer(r'class="img-modbox"', html or ""):
        start = m.end()
        nxt = html.find('class="img-modbox"', start)
        seg = html[start:nxt if nxt > 0 else len(html)]
        out.append(seg)
    return out


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.site = SITE

    def getName(self):
        return "最全短剧"

    def init(self, extend=""):
        import json as _json
        s = (extend or "").strip()
        if s:
            try:
                j = _json.loads(s)
                u = (j.get("sites") or "").strip()
            except Exception:
                u = s
            if u:
                self.site = u.rstrip("/")
        if not self.site:
            self.site = SITE

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, path, referer=True):
        hdrs = {"User-Agent": UA}
        if referer:
            hdrs["Referer"] = self.site + "/"
        try:
            return requests.get(path, headers=hdrs, timeout=15).text
        except Exception:
            return ""

    @staticmethod
    def _share_urls(html):
        seen, out = set(), []
        for u in RE_SHARE_URL.findall(html or ""):
            u = u.strip().strip('"\'')
            if u and u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def homeContent(self, filter):
        cats = [{"type_id": "2", "type_name": "最近更新"},
                {"type_id": "1", "type_name": "热门短剧"},
                {"type_id": "4", "type_name": "动漫短剧"},
                {"type_id": "3", "type_name": "其它短剧"}]
        result = {"class": cats, "filters": {}, "list": []}
        try:
            html = self._get(self.site + "/")
            for seg in _blocks(html):
                am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>', seg)
                if not am:
                    continue
                href = am.group(1).strip()
                tm = re.search(r'title="([^"]*)"', seg)
                name = tm.group(1) if tm else _text(re.sub(r'^.*?<a[^>]*>', '', seg, count=1))
                name = name.strip()
                if not name:
                    continue
                im = re.search(r'(?:data-original|src)="([^"]+)"', seg)
                pic = ""
                if im:
                    pic = im.group(1)
                    if not pic.startswith("http"):
                        pic = self.site + ("/" if not pic.startswith("/") else "") + pic
                fm = re.search(r'class="fr"[^>]*>([^<]*)<', seg)
                remark = fm.group(1).strip() if fm else ""
                result["list"].append({"vod_id": href, "vod_name": name,
                                       "vod_pic": pic, "vod_remarks": remark})
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("2", 1, False, {})

    def _parse_list(self, html):
        out = []
        for seg in _blocks(html):
            am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>', seg)
            if not am:
                continue
            href = am.group(1).strip()
            tm = re.search(r'title="([^"]*)"', seg)
            if tm:
                name = tm.group(1).strip()
            else:
                seg2 = re.sub(r'^.*?<a[^>]*>', '', seg, count=1)
                name = _text(seg2)
            if not name:
                continue
            im = re.search(r'(?:data-original|src)="([^"]+)"', seg)
            pic = ""
            if im:
                pic = im.group(1)
                if not pic.startswith("http"):
                    pic = self.site + ("/" if not pic.startswith("/") else "") + pic
            fm = re.search(r'class="fr"[^>]*>([^<]*)<', seg)
            remark = fm.group(1).strip() if fm else ""
            out.append({"vod_id": href, "vod_name": name, "vod_pic": pic, "vod_remarks": remark})
        return out

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 30, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            url = f"{self.site}/?cate={quote(str(tid))}&page={pg}"
            html = self._get(url)
            result["list"] = self._parse_list(html)
            # 分页: 最后一页 div.pagebar a href page=
            pages = 0
            for am in re.finditer(r'<a[^>]+href="([^"]*page=(\d+)[^"]*)"', html):
                pages = max(pages, int(am.group(2)))
            result["page"] = pg
            if pages > 0:
                result["pagecount"] = pages
                result["total"] = pages * max(len(result["list"]), 1)
            else:
                result["pagecount"] = pg + 1 if result["list"] else pg
                result["total"] = (pg + 1) * max(len(result["list"]), 1)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            if vid.startswith("search@@@"):
                parts = vid.split("@@@", 2)
                name = _text(parts[1]) if len(parts) > 1 else ""
                link = parts[2].strip() if len(parts) > 2 else ""
                vod = {"vod_id": vid, "vod_name": name, "vod_content": link}
                urls = []
                if link:
                    urls.append(f"分享1${link}")
                vod["vod_play_from"] = "网盘" if urls else ""
                vod["vod_play_url"] = "#".join(urls)
                return {"list": [vod]}
            if not vid.startswith("http"):
                vid = self.site + vid
            html = self._get(vid)
            name = ""
            tm = re.search(r"<title>([^<]+)</title>", html or "")
            if tm:
                name = tm.group(1).strip()
            content = ""
            cm = re.search(r'class="tx-text"[^>]*>([\s\S]*?)</', html or "")
            if cm:
                content = _text(cm.group(1))
            shares = self._share_urls(html)
            urls = []
            for i, u in enumerate(shares, 1):
                urls.append(f"分享{i}${u}")
            vod = {
                "vod_id": str(ids[0]),
                "vod_name": name or "短剧",
                "vod_content": content,
                "vod_play_from": "网盘" if urls else "",
                "vod_play_url": "#".join(urls),
                "vod_remarks": "" if urls else "未识别到夸克/百度分享链",
            }
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        # 原版需夸克/百度 token 解析;原样返回分享链
        return {"parse": 0, "url": (playId or "").strip(), "header": {"User-Agent": UA}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            url = f"{self.site}/so/search.php?act=search&q={quote(key)}&page={pg}"
            html = self._get(url)
            seen, out = set(), []
            for m in RE_SHARE_BLOCK.finditer(html or ""):
                name = _text(m.group(1))
                link = m.group(2)
                k = f"{name}|{link}"
                if k in seen:
                    continue
                seen.add(k)
                provider = "夸克" if "pan.quark.cn" in link else ("百度" if "pan.baidu.com" in link else "网盘")
                out.append({"vod_id": f"search@@@{name}@@@{link}",
                            "vod_name": name, "vod_pic": "", "vod_remarks": provider})
            if not out:
                for seg in _blocks(html):
                    am = re.search(r'<a[^>]+href="([^"]+)"[^>]*>', seg)
                    tm = re.search(r'title="([^"]*)"', seg)
                    if not am or not tm:
                        continue
                    name = tm.group(1).strip()
                    if not name:
                        continue
                    out.append({"vod_id": am.group(1).strip(), "vod_name": name,
                                "vod_pic": "", "vod_remarks": ""})
            result["list"] = out
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
