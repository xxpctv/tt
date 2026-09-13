# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   热播 (AppRJ)
# 说明: 完整复刻; multipart/form-data + timestamp/sign(MD5, salt 内置) 签名.
#       ext: {"url":"https://..."} 全接口可用: 首页/分类(过滤)/详情(多线路)/播放(多解析站)/搜索.

from base.spider import Spider
import requests
import re
import json
import time
import hashlib

SALT = "7gp0bnd2sr85ydii2j32pcypscoc4w6c7g5spl"
UA = "okhttp-okgo/jeasonlzy"


def _md5(s):
    return hashlib.md5(s.encode()).hexdigest()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.a = ""

    def getName(self):
        return "热播"

    def init(self, extend=""):
        try:
            j = json.loads((extend or "").strip() or "{}")
            self.a = re.sub(r"/+$", "", str(j.get("url") or ""))
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _sign(self):
        ts = str(int(time.time()))
        return {"timestamp": ts, "sign": _md5(SALT + ts)}

    def _post(self, path, params):
        try:
            data = dict(params)
            data.update(self._sign())
            r = requests.post(self.a + path, data=data,
                              headers={"User-Agent": UA}, timeout=15)
            t = (r.text or "").strip()
            return json.loads(t) if t.startswith("{") else {}
        except Exception:
            return {}

    def _list(self, j):
        data = (j or {}).get("data") or {}
        out = []
        for it in data.get("list") or []:
            if not isinstance(it, dict):
                continue
            pic = str(it.get("vod_pic") or "")
            if not pic:
                pic = str(it.get("vod_pic_thumb") or "")
            out.append({"vod_id": str(it.get("vod_id") or ""),
                        "vod_name": str(it.get("vod_name") or ""),
                        "vod_pic": pic,
                        "vod_remarks": str(it.get("vod_remarks") or "")})
        return out

    def _filters(self, obj):
        fts = []
        for key, name in (("class", "类型"), ("area", "地区"),
                          ("year", "年份"), ("lang", "语言")):
            arr = obj.get(key)
            if isinstance(arr, list) and len(arr) > 1:
                vals = [str(v) for v in arr if v and len(str(v)) > 1]
                if len(vals) > 1:
                    fts.append({"key": key, "name": name,
                                "value": [{"n": v, "v": v} for v in vals]})
        return fts

    def homeContent(self, filter):
        cats, fts = [], {}
        try:
            j = self._post("/v3/type/top_type", {})
            for it in (j.get("data") or {}).get("list") or []:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("type_id") or "")
                if not tid:
                    continue
                cats.append({"type_id": tid, "type_name": str(it.get("type_name") or "")})
                fl = self._filters(it)
                if fl:
                    fts[tid] = fl
        except Exception:
            pass
        return {"class": cats, "filters": fts, "list": []}

    def homeVideoContent(self):
        lst = self.categoryContent("1", "1", False, {})["list"]
        if not lst:
            lst = self.categoryContent("10", "1", False, {})["list"]
        return {"list": lst}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 12, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            params = {"type_id": str(tid), "limit": "12", "page": pg}
            ex = extend or {}
            for k in ("area", "class", "lang", "year"):
                v = str(ex.get(k) or "").strip()
                if v:
                    params[k] = v
            j = self._post("/v3/home/type_search", params)
            lst = self._list(j)
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = n if not lst else n + 1
            result["total"] = len(lst)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            j = self._post("/v3/home/vod_details", {"vod_id": vid})
            d = j.get("data") or {}
            if not d:
                return {"list": [], "error": "详情为空"}
            vod = {"vod_id": vid,
                   "vod_name": str(d.get("vod_name") or ""),
                   "vod_pic": str(d.get("vod_pic") or "") or str(d.get("vod_pic_thumb") or ""),
                   "vod_remarks": str(d.get("vod_remarks") or ""),
                   "vod_content": str(d.get("vod_content") or ""),
                   "vod_year": str(d.get("vod_year") or ""),
                   "vod_actor": str(d.get("vod_actor") or ""),
                   "vod_director": str(d.get("vod_director") or "")}
            froms, urls = [], []
            for pl in d.get("vod_play_list") or []:
                if not isinstance(pl, dict):
                    continue
                name = str(pl.get("name") or "")
                ua = str(pl.get("ua") or "")
                parses = "@".join(str(x) for x in (pl.get("parse_urls") or []))
                eps = []
                for u in pl.get("urls") or []:
                    if not isinstance(u, dict):
                        continue
                    eps.append(f"{u.get('name') or '播放'}${parses}|{u.get('url') or ''}|{ua}|{d.get('vod_class') or ''}|{u.get('nid') or ''}")
                if eps:
                    froms.append(name)
                    urls.append("#".join(eps))
            if froms:
                vod["vod_play_from"] = "$$$".join(froms)
                vod["vod_play_url"] = "$$$".join(urls)
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            parts = str(playId or "").split("|")
            if len(parts) == 5:
                parts = [parts[0], parts[1], parts[2], parts[3], parts[4]]
            if len(parts) < 2:
                return {"parse": 0, "url": "", "header": {}, "error": "播放参数错误"}
            parse_urls = parts[0]
            url = parts[1]
            ua = parts[2] if len(parts) > 2 else ""
            final_url, final_ua = "", ua
            for pu in parse_urls.split("@"):
                if not pu:
                    final_ua = ua
                    continue
                ts = str(int(time.time()))
                try:
                    r = requests.get(f"{pu}{url}&sign={_md5(SALT + ts)}&timestamp={ts}",
                                     timeout=15)
                    t = (r.text or "").strip()
                    if not t.startswith("{"):
                        final_ua = ua
                        continue
                    j = json.loads(t)
                    u = str(j.get("url") or "")
                    final_ua = str(j.get("UA") or "") or ua
                    if u.startswith("http"):
                        final_url = u
                        break
                    final_ua = ua
                except Exception:
                    final_ua = ua
                    continue
            if not final_url.startswith("http"):
                return {"parse": 0, "url": "", "header": {}, "error": "无播放地址"}
            return {"parse": 0, "url": final_url,
                    "header": {"User-Agent": final_ua} if final_ua else {}}
        except Exception:
            return {"parse": 0, "url": "", "header": {}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            j = self._post("/v3/home/search",
                           {"keyword": key, "limit": "12", "page": "1"})
            result["list"] = self._list(j)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
