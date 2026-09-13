# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   飞卢听书 (FeiLu)
# 站点: https://ts.faloo.com  (GB18030)

from base.spider import Spider
import requests
import re
from urllib.parse import quote

BASE = "https://ts.faloo.com"
UA = "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
FALLBACK_CATES = [["0", "全部书库"], ["1", "玄幻奇幻"], ["6", "武侠仙侠"], ["4", "都市言情"],
                  ["7", "青春校园"], ["3", "军事历史"], ["2", "科幻网游"], ["44", "耽美同人"],
                  ["5", "恐怖灵异"], ["9", "短篇"], ["54", "古典大作"], ["89", "人文"], ["90", "历史"]]
RE_LISTEN = re.compile(r"/listen/(\d+)\.html")
RE_MP3 = re.compile(r"(http://tss\.faloo\.com/ListenNode/[^\"'<>]+\.mp3)")
RE_CATE = re.compile(r"/category/(\d+)/")
RE_PAGE = re.compile(r"/category/\d+(?:/0/\d+)?/(\d+)\.html")


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _abs(u):
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        return BASE + u
    return BASE + "/" + u


class Spider(Spider):
    def getName(self):
        return "飞卢听书"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Referer": BASE + "/",
                                           "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=15)
            r.encoding = "gb18030"
            return r.text
        except Exception:
            return ""

    def _parse_list(self, html):
        out, seen = [], set()
        # 优先 audio_info 块, 回退全部 listen 链接
        for m in RE_LISTEN.finditer(html or ""):
            lid = m.group(1)
            if lid in seen:
                continue
            seen.add(lid)
            out.append(lid)
        vods = []
        for lid in out:
            vods.append({"vod_id": lid, "vod_name": "听书", "vod_pic": "",
                         "vod_remarks": ""})
        return vods

    def homeContent(self, filter):
        cats = []
        try:
            html = self._get(BASE + "/Category.aspx")
            seen = set()
            for m in RE_CATE.finditer(html or ""):
                cid = m.group(1)
                if cid in seen:
                    continue
                seen.add(cid)
                cats.append({"type_id": cid, "type_name": cid})
        except Exception:
            pass
        if not cats:
            cats = [{"type_id": c[0], "type_name": c[1]} for c in FALLBACK_CATES]
        else:
            cats.insert(0, {"type_id": "0", "type_name": "全部书库"})
        filters = {"sort": [{"key": "sort", "name": "排序",
                             "value": [{"n": "综合", "v": "0"}, {"n": "播放最多", "v": "1"},
                                       {"n": "最近更新", "v": "5"}]}]}
        return {"class": cats, "filters": filters, "list": self._parse_list(self._get(BASE + "/"))}

    def homeVideoContent(self):
        return self.categoryContent("0", 1, False, {})

    @staticmethod
    def _cate_url(tid, pg, sort):
        tid = str(tid or "") or "0"
        pg = str(pg or "") or "1"
        if sort and str(sort) != "0":
            return f"{BASE}/category/{tid}/0/{sort}/{pg}.html"
        return f"{BASE}/category/{tid}/{pg}.html"

    def _vods_from(self, html):
        # 复用 c(): 提取 listen 链接 + 名称/图/备注(简化: 从音频块提取)
        out, seen = [], set()
        for m in RE_LISTEN.finditer(html or ""):
            lid = m.group(1)
            if lid in seen:
                continue
            seen.add(lid)
            out.append(lid)
        return out

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            sort = (extend or {}).get("sort") or ""
            url = self._cate_url(tid, pg, sort)
            html = self._get(url)
            ids = self._vods_from(html)
            names = self._names_from(html, ids)
            for i, lid in enumerate(ids):
                result["list"].append({"vod_id": lid, "vod_name": names.get(lid) or f"听书 {lid}",
                                       "vod_pic": "", "vod_remarks": ""})
            # 分页
            max_pg = pg
            for m in RE_PAGE.finditer(html or ""):
                n = int(m.group(1))
                if n > max_pg:
                    max_pg = n
            if "下一页" in html and max_pg <= pg:
                max_pg = pg + 1
            result["page"] = pg
            result["pagecount"] = max(pg, max_pg)
            result["total"] = max(len(ids), 1) * max(pg, max_pg)
        except Exception:
            pass
        return result

    def _names_from(self, html, ids):
        # 从页面 a[href=/listen/x.html] 提取书名 title
        names = {}
        for m in re.finditer(r'<a[^>]+href="([^"]*listen/(\d+)\.html[^"]*)"[^>]*title="([^"]*)"', html or ""):
            lid = m.group(2)
            if lid in ids:
                names[lid] = m.group(3).strip()
        for m in re.finditer(r'href="([^"]*listen/(\d+)\.html[^"]*)"[^>]*>\s*<[^>]+>\s*([^<]{1,40})<', html or ""):
            lid = m.group(2)
            if lid in ids and lid not in names:
                names[lid] = _text(m.group(3))
        return names

    def detailContent(self, ids):
        vod = {}
        try:
            lid = str(ids[0])
            html = self._get(f"{BASE}/listen/{lid}.html")
            title = ""
            m = re.search(r"<title>([^<]+)</title>", html or "")
            if m:
                t = m.group(1).strip()
                m2 = re.search(r"【听书】(.+?)[|\s]", t)
                if m2:
                    title = m2.group(1).strip()
                else:
                    title = t.split("|")[0].replace("【听书】", "")
            mps, seen = [], set()
            for u in RE_MP3.findall(html or ""):
                if u not in seen:
                    seen.add(u)
                    mps.append(u)
            # 尝试匹配页面集标签
            labels = re.findall(r"(第\s*\d+\s*[集章])", html or "")
            eps = []
            for i, u in enumerate(mps):
                lb = labels[i] if i < len(labels) else f"第{i + 1}集"
                eps.append(f"{lb}${u}")
            vod = {"vod_id": lid, "vod_name": title or f"听书 {lid}",
                   "vod_pic": "",
                   "vod_remarks": f"{len(eps)}集",
                   "vod_play_from": "飞卢听书",
                   "vod_play_url": "#".join(eps),
                   "vod_content": "飞卢听书 · 有声小说"}
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        return {"parse": 0, "url": (playId or "").strip(),
                "header": {"User-Agent": UA, "Referer": BASE + "/",
                           "Accept-Language": "zh-CN,zh;q=0.9"}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            kw = quote(key, encoding="gbk", errors="replace")
            html = self._get(f"{BASE}/list.aspx?k={kw}")
            ids = self._vods_from(html)
            names = self._names_from(html, ids)
            for lid in ids:
                result["list"].append({"vod_id": lid, "vod_name": names.get(lid) or key,
                                       "vod_pic": "", "vod_remarks": ""})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
