# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   移动4K云盘 (YiDong4K)
# 注意: 详情里的播放地址为天翼云(139)分享链, 需账号 token 才能解析为直链,
#      在详情页以"分享链:"文本展示; 列表/搜索/详情结构完整可用.

from base.spider import Spider
import requests
import hashlib
import time
import json

BASE = "https://vidsite.cloudseekr.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://vidsite.cloudseekr.com",
    "Referer": "https://vidsite.cloudseekr.com/vid/app/",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self._fprint = ""

    def getName(self):
        return "移动4K云盘"

    def init(self, extend=""):
        if not self._fprint:
            self._fprint = _md5(f"AiNewYiDong4K_{int(time.time() * 1000)}_{time.time_ns()}")

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _post(self, action, obj):
        try:
            r = requests.post(f"{BASE}/vidsite/vs/{action}", data=json.dumps(obj, ensure_ascii=False),
                              headers=HEADERS, timeout=15)
            return r.json()
        except Exception:
            return {}

    @staticmethod
    def _remark(it):
        score = str(it.get("score") or "").strip()
        if score and score not in ("0", "0.0"):
            return score
        up = str(it.get("updateTime") or "").strip()
        return up[:10] if len(up) >= 10 else ""

    @staticmethod
    def _cover(it):
        for k in ("appCoverUrl", "pcCoverUrl"):
            v = str(it.get(k) or "").strip()
            if v and v != "null":
                return v
        return ""

    def homeContent(self, filter):
        return {"class": [{"type_id": "1", "type_name": "电影"},
                          {"type_id": "2", "type_name": "电视剧"},
                          {"type_id": "3", "type_name": "动漫"}],
                "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("1", 1, False, {})

    def _qry(self, column, pg, key=None):
        body = {"columnId": column, "cateIdList": [0, 0, 0],
                "pageIndex": pg, "pageSize": 9}
        if key:
            body["searchKey"] = key
        return self._post("qryPageColumnVideo", body)

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 9, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            col = int(str(tid).strip() or 1)
            j = self._qry(col, pg)
            if str(j.get("code")) != "000000":
                return result
            data = j.get("data") or {}
            for it in data.get("list") or []:
                vid = str(it.get("id") or "").strip()
                title = str(it.get("title") or "").strip()
                if not vid or vid == "null" or not title:
                    continue
                result["list"].append({"vod_id": vid, "vod_name": title,
                                       "vod_pic": self._cover(it),
                                       "vod_remarks": self._remark(it)})
            total = int(data.get("total") or len(result["list"]))
            pages = int(data.get("pages") or ((total + 8) // 9 if total > 0 else pg))
            result["page"] = pg
            result["pagecount"] = max(pg, pages)
            result["total"] = total
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            body = {"videoId": int(vid) if str(vid).isdigit() else 0, "fprint": self._fprint}
            self._post("addAccessRecord", body)
            j = self._post("qryVideoDetail", body)
            if str(j.get("code")) != "000000":
                return {"list": []}
            d = j.get("data")
            if not d:
                return {"list": []}
            content = d.get("remark") or d.get("description") or d.get("intro") or ""
            res = str(d.get("resUrl") or "").strip()
            if res:
                content = f"{content}\n分享链: {res}"
            cats = "/".join([str(x).strip() for x in (d.get("cateNameList") or [])
                             if str(x).strip() and str(x).strip() != "null"])
            vod = {
                "vod_id": vid,
                "vod_name": d.get("title") or "",
                "vod_pic": self._cover(d),
                "vod_actor": d.get("actor") or "",
                "vod_director": d.get("director") or "",
                "vod_content": content,
                "vod_remarks": self._remark(d),
                "type_name": cats,
                "vod_play_from": "",
                "vod_play_url": "",
            }
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        # 原版需 139 云盘 token (PanWebSite.guardLogin) 解析;原样返回
        return {"parse": 0, "url": (playId or "").strip(), "header": {}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 9, "total": 0}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            pg = int(pg) if str(pg).isdigit() else 1
            j = self._qry(0, pg, key)
            if str(j.get("code")) != "000000":
                return result
            data = j.get("data") or {}
            for it in data.get("list") or []:
                vid = str(it.get("id") or "").strip()
                title = str(it.get("title") or "").strip()
                if not vid or vid == "null" or not title:
                    continue
                result["list"].append({"vod_id": vid, "vod_name": title,
                                       "vod_pic": self._cover(it),
                                       "vod_remarks": self._remark(it)})
            total = int(data.get("total") or len(result["list"]))
            pages = int(data.get("pages") or ((total + 8) // 9 if total > 0 else pg))
            result["page"] = pg
            result["pagecount"] = max(pg, pages)
            result["total"] = total
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
