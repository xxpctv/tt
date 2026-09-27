# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   荐片 (JianPian)
# 说明: 完整复刻; 域名经 DNS TXT(swrdsfeiujo25sw.cc) 动态解析 + 图床资源域探测;
#       列表/详情/搜索/播放(大站直连, 其余走通用解析) 全可用.

from base.spider import Spider
import requests
import re
import json
import random
from urllib.parse import quote

UA = ("Mozilla/5.0 (Linux; Android 7.1.2; V2049A Build/UP1A.231005.007; wv) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/81.0.4044.117 "
      "Mobile Safari/537.36;webank/h5face;webank/1.0;netType:NETWORK_WIFI;"
      "appVersion:422;packageName:com.jp3.xg3")
BIG_SITES = ["iqiyi.com", "v.qq.com", "youku.com", "le.com", "tudou.com",
             "mgtv.com", "sohu.com", "acfun.cn", "bilibili.com", "baofeng.com",
             "pptv.com", "www.miguvideo.com", "www.ixigua.com",
             "vip.1905.com", "www.fun.tv", "m.fun.tv"]
CATS = [["1", "电影"], ["2", "电视剧"], ["3", "动漫"], ["4", "综艺"], ["67", "短剧"]]
CATEGORY_IDS = [("全部", ""), ("言情", "70"), ("爱情", "71"), ("战神", "72"),
                ("古代", "73"), ("萌娃", "74"), ("神医", "75"), ("玄幻", "76"),
                ("重生", "77"), ("穿越", "80"), ("闪婚", "112")]


def _pick_pic(obj):
    """tvimg/path/cover_image/thumbnail 第一个非 webp/avif"""
    cands = []
    for k in ("tvimg", "path", "cover_image", "thumbnail"):
        v = obj.get(k)
        if isinstance(v, str) and v and v not in cands:
            cands.append(v)
    for c in cands:
        low = c.lower()
        if ".webp" not in low and ".avif" not in low:
            return c
    return cands[0] if cands else ""


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.a = ""   # api 域名
        self.b = ""   # 图床域名

    def getName(self):
        return "荐片"

    def init(self, extend=""):
        try:
            self._resolve()
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _get(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            return r.text if r.status_code == 200 else ""
        except Exception:
            return ""

    def _resolve(self):
        try:
            j = json.loads(self._get("https://dns.alidns.com/resolve?name=swrdsfeiujo25sw.cc&type=TXT"))
            ans = (j.get("Answer") or [{}])[0].get("data") or ""
            domains = [d.strip().strip('"') for d in ans.split(",") if d.strip()]
            for d in domains:
                u = self._prefix(d)
                if self._probe(u):
                    self.a = u
                    self.b = self._img_domain(u)
                    return
            if domains:
                u = self._prefix(domains[0])
                self.a = u
                self.b = self._img_domain(u)
        except Exception:
            pass

    def _prefix(self, d):
        if d.startswith("http"):
            return d
        if d.startswith("www.") or "." in d:
            rnd = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789")
                          for _ in range(6))
            return "https://" + rnd + "." + d
        return "https://" + d

    def _probe(self, u):
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=8)
            return r.status_code == 200 and len(r.text or "") > 100
        except Exception:
            return False

    def _img_domain(self, u):
        try:
            j = json.loads(self._get(u + "/api/v2/settings/resourceDomainConfig"))
            d = (j.get("data") or {}).get("imgDomain") or ""
            return d.split(",")[0].strip() or u
        except Exception:
            return u

    def _fix(self, url):
        """相对/裸地址补全 + 图床走本地代理"""
        u = (url or "").strip()
        if not u:
            return ""
        if u.startswith("proxy://"):
            return u
        if u.startswith("http"):
            return u
        if u.startswith("/") and self.b:
            return self.b + u
        if u.startswith("/"):
            return self.a + u
        return u

    def _api_url(self, path):
        return (self.a if self.a else "https://") + path

    def _build_vod(self, obj, cat):
        title = str(obj.get("title") or "")
        cover = _pick_pic(obj)
        pic = self._fix(cover)
        mask = str(obj.get("mask") or "")
        if not mask:
            mask = str(obj.get("score") or "")
        vid = str(obj.get("id") or "")
        return {"vod_id": f"{vid}$$${title}$$${cover}$$${cat}",
                "vod_name": title, "vod_pic": pic, "vod_remarks": mask}

    def homeContent(self, filter):
        fts = {}
        for cid, _ in CATS:
            f = []
            if cid != "67":
                f = [{"key": "area", "name": "地区",
                      "value": [{"n": n, "v": v} for n, v in
                                [("全部", ""), ("国产", "1"), ("中国香港", "3"),
                                 ("中国台湾", "6"), ("美国", "5"), ("韩国", "18"), ("日本", "2")]]},
                     {"key": "year", "name": "年份",
                      "value": [{"n": "全部", "v": ""}, {"n": "2026", "v": "162"},
                                {"n": "2025", "v": "107"}, {"n": "2024", "v": "119"},
                                {"n": "2023", "v": "153"}, {"n": "2022", "v": "101"},
                                {"n": "2021", "v": "118"}, {"n": "2020", "v": "16"},
                                {"n": "2019", "v": "7"}, {"n": "2018", "v": "2"},
                                {"n": "2017", "v": "3"}, {"n": "2016", "v": "22"}]},
                     {"key": "sort", "name": "排序",
                      "value": [{"n": "热门", "v": "hot"}, {"n": "更新", "v": "update"},
                                {"n": "评分", "v": "rating"}]}]
            else:
                f = [{"key": "category_id", "name": "类型",
                      "value": [{"n": n, "v": v} for n, v in CATEGORY_IDS]}]
            fts[cid] = f
        return {"class": [{"type_id": cid, "type_name": name} for cid, name in CATS],
                "filters": fts, "list": []}

    def homeVideoContent(self):
        result = {"list": []}
        try:
            if not self.a:
                return result
            j = json.loads(self._get(self._api_url("/api/dyTag/list?category_id=88")))
            for sec in j.get("data") or []:
                for it in sec.get("dataList") or []:
                    result["list"].append(self._build_vod(it, "1"))
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 30, "total": 0}
        try:
            if not self.a:
                result["error"] = "域名解析失败, 请稍后重试"
                return result
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            cat = str(tid)
            if cat == "67":
                url = f"{self.a}/api/crumb/shortList?fcate_pid={cat}&category_id={ex.get('category_id') or ''}&sort=update&page={pg}"
                key = "cover_image"
            else:
                url = (f"{self.a}/api/crumb/list?fcate_pid={cat}&category_id="
                       f"&area={ex.get('area') or ''}&year={ex.get('year') or ''}"
                       f"&type={ex.get('type') or ''}&sort={ex.get('sort') or ''}&page={pg}")
                key = "path"
            j = json.loads(self._get(url))
            lst = []
            for it in j.get("data") or []:
                lst.append(self._build_vod(it, cat))
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = n
            result["total"] = len(lst)
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            if not self.a:
                return {"list": [], "error": "域名解析失败"}
            parts = str(ids[0]).split("$$$", -1)
            if len(parts) < 4:
                return {"list": [], "error": "详情参数错误"}
            vid, title, cover, cat = parts[0], parts[1], parts[2], parts[3]
            pic = self._fix(cover)
            if cat == "67":
                j = json.loads(self._get(f"{self.a}/api/detail?vid={vid}"))
            else:
                j = json.loads(self._get(f"{self.a}/api/video/detailv2?id={vid}"))
            data = j.get("data") or {}
            vod = {"vod_id": str(ids[0]), "vod_name": title, "vod_pic": pic,
                   "vod_content": str(data.get("description") or ""),
                   "vod_year": str(data.get("year") or ""),
                   "vod_area": str(data.get("area") or "")}
            actors = []
            for a in data.get("actors") or []:
                nm = a.get("name") if isinstance(a, dict) else ""
                if nm:
                    actors.append(str(nm))
            if actors:
                vod["vod_actor"] = ",".join(actors)
            play_from, play_url = [], []
            if cat == "67":
                eps = []
                for pl in data.get("playlist") or []:
                    if isinstance(pl, dict) and pl.get("url"):
                        eps.append(f"{pl.get('title') or '正片'}${pl['url']}")
                if eps:
                    play_from.append("常规线路")
                    play_url.append("#".join(eps))
            else:
                for src in data.get("source_list_source") or []:
                    nm = src.get("name") if isinstance(src, dict) else ""
                    eps = []
                    for s in (src.get("source_list") or []):
                        if not isinstance(s, dict):
                            continue
                        u = str(s.get("url") or "")
                        if not u:
                            continue
                        if u.startswith("ftp"):
                            u = "tvbox-xg:" + u
                        eps.append(f"{s.get('source_name') or '播放'}${u}")
                    if eps:
                        play_from.append(str(nm) if nm else f"线路{len(play_from) + 1}")
                        play_url.append("#".join(eps))
            if play_from:
                vod["vod_play_from"] = "$$$".join(play_from)
                vod["vod_play_url"] = "$$$".join(play_url)
            else:
                vod["vod_remarks"] = "无播放源"
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            url = (playId or "").strip()
            if not url:
                return {"parse": 0, "url": "", "header": {}, "error": "播放地址为空"}
            if url.startswith("tvbox-xg:"):
                return {"parse": 0, "url": "ftp" + url[9:], "header": {}}
            host = url.replace("https://", "").replace("http://", "")
            if "/" in host:
                host = host.split("/", 1)[0]
            path = url[url.find("://") + 3:]
            path = path[path.find("/"):] if "/" in path else ""
            jx = False
            for s in BIG_SITES:
                if host == s or host.endswith("." + s) or host == s[4:] if s.startswith("www.") else False:
                    jx = True
                    break
                if s.startswith("www.") and host == s[4:]:
                    jx = True
                    break
                if host.endswith("." + s):
                    jx = True
                    break
            if jx and not (("iqiyi.com" in host) and ("/a_" in path or "/w_" in path or "/v_" in path)):
                return {"parse": 1, "url": url, "header": {}, "jx": 1}
            return {"parse": 0, "url": url, "header": {"User-Agent": UA}}
        except Exception:
            return {"parse": 0, "url": playId or "", "header": {}}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            if not self.a:
                return result
            key = str(key or "").strip()
            if not key:
                return result
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            j = json.loads(self._get(f"{self.a}/api/v2/search/videoV2?key={quote(key)}"
                                     f"&category_id=88&page={pg}&pageSize=20"))
            kw = key.lower()
            for it in j.get("data") or []:
                top = it.get("top_category") or {}
                cat = str(top.get("id") or "1") if isinstance(top, dict) else "1"
                # 搜索过滤：标题 OR 演员命中才保留
                tname = str(it.get("title") or "")
                actors = " ".join(str(a.get("name") or "") for a in (it.get("actors") or []) if isinstance(a, dict))
                if kw and kw not in tname.lower() and kw not in actors.lower():
                    continue
                result["list"].append(self._build_vod(it, cat))
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
