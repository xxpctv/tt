# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   童趣 (TongQu)
# 站点: https://www.boosj.com
# 说明: 完整复刻 分类(含年龄段/排序过滤)/首页推荐/详情/搜索;
#       播放走 gslb 接口(Referer 校验) 返回直链.

from base.spider import Spider
import requests
import re
import json
from urllib.parse import quote

UA = ("Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36")
HOME = "https://www.boosj.com/"
GSLB = "https://gslb.boosj.com/gslbm"
CATS = [["all", "全部"], ["28", "辅食"], ["582", "动画"], ["3364", "儿童舞蹈"],
        ["3366", "少儿英语"], ["3367", "儿童歌曲"], ["3622", "才艺"],
        ["3782", "播视自制"], ["3822", "故事"], ["3842", "亲子教育"],
        ["4402", "美术"], ["4583", "其他"], ["4762", "儿童游戏"],
        ["4842", "识物"], ["4843", "绘本"], ["4844", "古诗"], ["4845", "科普"],
        ["5102", "儿童玩具"], ["5142", "播视童趣儿童玩具"]]
FILTERS = [["area", "年龄段", [("全部", ""), ("6岁以上", "?p367=370"),
                              ("3~6岁", "?p367=369"), ("0~3岁", "?p367=368")]],
           ["by", "排序", [("全部", ""), ("最新发布", "lately"),
                           ("最多播放", "pop"), ("最多评论", "view")]]]


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


class Spider(Spider):
    def getName(self):
        return "童趣"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _fetch(self, url):
        try:
            return requests.get(url, headers={"User-Agent": UA, "Referer": HOME},
                                timeout=15).text
        except Exception:
            return ""

    def _parse_block(self, html, pattern):
        out, seen = [], set()
        for m in re.finditer(pattern, html or ""):
            seg = m.group(1)
            idm = re.search(r"boosj\.com/(\d+)\.html", seg)
            if not idm:
                continue
            vid = idm.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            name = vid
            tm = re.search(r'<h3>[\s\S]*?title="([^"]+)"', seg)
            if not tm:
                tm = re.search(r'title="([^"]+)"', seg)
            if tm:
                name = tm.group(1).strip()
            pic = ""
            im = re.search(r'(?:data-original|src)="([^"]+)"', seg)
            if im:
                pic = im.group(1)
                if pic.startswith("//"):
                    pic = "https:" + pic
            remark = ""
            rm = re.search(r'class="played">([^<]*)</span>', seg)
            if rm:
                remark = rm.group(1).strip()
            out.append({"vod_id": vid, "vod_name": name,
                        "vod_pic": pic, "vod_remarks": remark})
        return out

    def homeContent(self, filter):
        fts = {}
        for cid, _ in CATS:
            fts[cid] = [{"key": k, "name": n,
                         "value": [{"n": nn, "v": vv} for nn, vv in vals]}
                        for k, n, vals in FILTERS]
        return {"class": [{"type_id": cid, "type_name": name} for cid, name in CATS],
                "filters": fts, "list": []}

    def homeVideoContent(self):
        html = self._fetch(HOME + "baby/")
        return {"list": self._parse_block(html, r'<div class="pubpic">([\s\S]*?)</div>\s*</div>')}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 24, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            ex = extend or {}
            cat = str(tid or "").lstrip("_")
            by = str(ex.get("by") or "")
            area = str(ex.get("area") or "")
            if not cat:
                # 全部: search_res_3362__{pg}...
                url = f"{HOME}search_res_3362__{pg if pg > 1 else ''}{'' if pg == 1 else '_'}{by}.html{area}"
            else:
                if pg == 1:
                    url = f"{HOME}search_res_3362__{cat}__{by}.html{area}"
                else:
                    url = f"{HOME}search_res_3362__{cat}_{pg}_{by}.html{area}"
            # 按原版逻辑兜底修正: 无 by 时省略尾段
            if not by and pg == 1:
                url = f"{HOME}search_res_3362__{cat}__.html{area}" if cat else \
                      f"{HOME}search_res_3362______.html{area}"
            html = self._fetch(url)
            lst = self._parse_block(html, r'<div class="bj-col4">([\s\S]*?)</div>\s*</div>')
            result["list"] = lst
            result["page"] = pg
            result["pagecount"] = pg if not lst else pg + 1
            result["total"] = 9999
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            html = self._fetch(f"{HOME}{vid}.html")
            name = vid
            m = re.search(r'<h2 class="video_title">([^<]+)</h2>', html or "")
            if m:
                name = m.group(1).strip()
            vod = {"vod_id": vid, "vod_name": name, "vod_pic": "",
                   "vod_play_from": "童趣", "vod_play_url": f"播放${vid}"}
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            m = re.search(r"(\d+)", playId or "")
            if not m:
                return {"parse": 0, "url": "", "header": {}}
            vid = m.group(1)
            cfg = json.loads(self._fetch(GSLB + "/ipv2.json") or "{}")
            cfg = dict(cfg)
            cfg["_id"] = vid
            url = GSLB + "?" + "&".join(
                f"{k}={quote(str(v), safe='')}" for k, v in cfg.items())
            headers = {"User-Agent": UA,
                       "Referer": f"{HOME}{vid}.html"}
            r = requests.get(url, headers=headers, timeout=15)
            j = json.loads(r.text or "{}")
            u = str(j.get("url") or "")
            t = str(j.get("t") or "")
            if u and t:
                u += "?" + t
            return {"parse": 0, "url": u, "header": headers}
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
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            j = json.loads(self._fetch(f"https://search.boosj.com/m_ajax?q={quote(key)}"
                                       f"&p={pg}&typeId=3362") or "{}")
            if j.get("code") != 200:
                return result
            for it in (j.get("body") or {}).get("result") or []:
                result["list"].append({"vod_id": str(it.get("id") or ""),
                                       "vod_name": str(it.get("resourceName") or ""),
                                       "vod_pic": str(it.get("imageUrl") or ""),
                                       "vod_remarks": str(it.get("clickNumStr") or "")})
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
