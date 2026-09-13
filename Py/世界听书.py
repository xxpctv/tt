# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   世界听书 (TingShijie)
# API: 远程配置 101.43.48.231:8090 (失败用默认 https://app.365ting.com/listen/Apitzg2025/)

from base.spider import Spider
import requests
import json
import hashlib
import time

API = "https://app.365ting.com/listen/Apitzg2025/"
CFG = "http://101.43.48.231:8090/config/tingchina2025.txt"
TOKEN = "J9gSpfUlzYxE8Hn5IXiGaD2jVMrwAm0K"
UA = "TingShiJie/1.8.8 (m.i275.com)"
CATES = [["6", "玄幻奇幻"], ["7", "都市言情"], ["8", "宫斗女频"], ["9", "官场商战"],
         ["10", "武侠仙侠"], ["11", "刑侦推理"], ["12", "探险科幻"], ["13", "重生穿越"],
         ["14", "恐怖惊悚"], ["15", "文学历史"], ["49", "两性情感"]]


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.api = API

    def getName(self):
        return "世界听书"

    def init(self, extend=""):
        try:
            r = requests.get(CFG, headers={"User-Agent": UA}, timeout=8)
            t = r.text.strip()
            if t:
                self.api = t if t.endswith("/") else t + "/"
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _json(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            return r.json()
        except Exception:
            return {}

    def homeContent(self, filter):
        return {"class": [{"type_id": c[0], "type_name": c[1]} for c in CATES], "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("6", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 100, "limit": 20, "total": 2000}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            j = self._json(f"{self.api}appHomeByCategory?categoryId={tid}&page={pg}&size=120")
            if j.get("status") != 0:
                return result
            for it in j.get("data") or []:
                bid = str(it.get("id") or "")
                title = str(it.get("bookTitle") or "")
                if not bid or not title:
                    continue
                result["list"].append({"vod_id": bid, "vod_name": title,
                                       "vod_pic": it.get("bookImage") or "",
                                       "vod_remarks": it.get("bookAnchor") or ""})
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            bid = str(ids[0])
            j = self._json(f"{self.api}book?bookId={bid}")
            if j.get("status") != 0:
                return {"list": []}
            d = (j.get("data") or {}).get("bookData") or {}
            count = int(d.get("count") or 0)
            eps = []
            pages = (count + 999) // 1000
            for p in range(1, pages + 1):
                cj = self._json(f"{self.api}chapter?size=1000&page={p}&sort=asc&bookId={bid}")
                if cj.get("status") != 0:
                    continue
                for it in (cj.get("data") or {}).get("list") or []:
                    pos = it.get("position")
                    cid = it.get("chapterId")
                    if pos is None or not cid:
                        continue
                    eps.append(f"{pos}${bid}|{cid}")
            vod = {"vod_id": bid,
                   "vod_name": d.get("bookTitle") or "",
                   "vod_pic": d.get("bookImage") or "",
                   "vod_content": d.get("bookDesc") or "",
                   "vod_play_from": "世界听书",
                   "vod_play_url": "#".join(eps)}
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            parts = str(playId or "").split("|")
            if len(parts) < 2:
                return {"parse": 0, "url": "", "header": {"User-Agent": UA}}
            bid, cid = parts[0], parts[1]
            ts = str(int(time.time() * 1000))
            sig = _md5(_md5(ts + TOKEN) + TOKEN)
            u = (f"{self.api}AppGetChapterUrl2023?timeStamp={ts}&uid=&chapterId={cid}"
                 f"&addItParapet={sig}&bookId={bid}")
            j = self._json(u)
            if j.get("status") == 0:
                url = j.get("src") or ""
        except Exception:
            pass
        return {"parse": 0, "url": url, "header": {"User-Agent": UA}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            j = self._json(f"{self.api}appSearch?client=babala-android&search={key}&app_token=abcSEARCH-2025")
            if j.get("status") != 0:
                return result
            for it in (j.get("data") or {}).get("bookData") or []:
                bid = str(it.get("id") or "")
                title = str(it.get("bookTitle") or "")
                if not bid or not title:
                    continue
                result["list"].append({"vod_id": bid, "vod_name": title,
                                       "vod_pic": it.get("bookImage") or "",
                                       "vod_remarks": it.get("bookAnchor") or ""})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
