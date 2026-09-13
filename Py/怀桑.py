# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   怀桑 (AppQi)
# 说明: 完整复刻; 响应 data 字段 AES-CBC/PKCS5 加密, key/iv 来自 ext datakey/dataiv.
#       ext: {"url":"https://...","datakey":"...","dataiv":"...","deviceId":"...","version":"...","ua":"...","init":"initV120","search":"searchList"}
#       或 site 指向 txt/json 多行配置(自动 HEAD 探测可用行).
#       首页/分类(过滤)/详情(多线路+AES播放参数)/播放(直链/解析/vodParse)/搜索 全可用.

from base.spider import Spider
import requests
import re
import json
import base64
import time
import hashlib
from urllib.parse import quote, urlencode
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36")
CFG_RE = re.compile(r"^https?://.*\.(txt|json)$", re.I)
MEDIA_RE = re.compile(r".*(m3u8|mp4|mkv).*", re.I)
RE_PARSE = re.compile(r"(parse_api=)(.*?)(?=&token)(&token)")
RE_URL = re.compile(r"(url=)(.*?)(?=&token)(&token)")


def _aes_cbc_enc(text, key, iv):
    pad = 16 - len(text.encode()) % 16
    data = text.encode() + bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()),
                    backend=default_backend())
    enc = cipher.encryptor().update(data) + cipher.encryptor().finalize()
    return base64.b64encode(enc).decode()


def _aes_cbc_dec(b64, key, iv):
    try:
        data = base64.b64decode((b64 or "").replace(" ", ""))
        cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()),
                        backend=default_backend())
        dec = cipher.decryptor().update(data) + cipher.decryptor().finalize()
        pad = dec[-1] if dec else 0
        if 1 <= pad <= 16:
            dec = dec[:-pad]
        return dec.decode("utf-8", "ignore")
    except Exception:
        return ""


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.a = {}      # init 配置
        self.host = ""
        self.b = ""      # AES key
        self.c = ""      # AES iv
        self.d = ""      # device id
        self.e = ""      # version
        self.ua = "okhttp/3.10.0"
        self.f = "initV120"
        self.g = "searchList"
        self._headers_map = {}

    def getName(self):
        return "怀桑"

    def init(self, extend=""):
        try:
            raw = (extend or "").strip()
            j = json.loads(raw) if raw.startswith("{") else {}
            host = j.get("url") or j.get("host") or ""
            if not host:
                site = j.get("site") or ""
                if CFG_RE.match(str(site)):
                    try:
                        r = requests.get(site, headers={"User-Agent": "okhttp/3.10.0"}, timeout=10)
                        lines = [ln.strip() for ln in re.split(r"\r?\n", r.text or "")
                                 if ln.strip().startswith("http")]
                    except Exception:
                        lines = []
                    for ln in lines:
                        try:
                            h = requests.head(ln.rstrip("/"), timeout=8)
                            if h.status_code not in (0, 404, 502, 503, 504):
                                host = ln
                                break
                        except Exception:
                            continue
            self.b = j.get("dataKey") or j.get("datakey") or j.get("key") or ""
            self.c = j.get("dataIv") or j.get("dataiv") or self.b
            self.d = str(j.get("deviceId") or "")
            self.e = str(j.get("version") or "")
            self.ua = str(j.get("ua") or "okhttp/3.10.0")
            self.f = str(j.get("init") or "initV120")
            self.g = str(j.get("search") or "searchList")
            if not host or not self.b:
                return
            self.host = re.sub(r"/+$", "", host)
            cfg = self.post_json(f"/qijiappapi.index/{self.f}", "{}")
            if isinstance(cfg, dict):
                self.a = cfg
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _headers(self, verify=True):
        h = dict(self._headers_map)
        h["User-Agent"] = self.ua
        h["app-user-device-id"] = self.d
        h["app-version-code"] = self.e
        h["app-ui-mode"] = "light"
        if verify:
            h["app-api-verify-time"] = str(int(time.time()))
        return h

    def post_json(self, path, body):
        try:
            r = requests.post(f"{self.host}/api.php{path}", data=body,
                              headers=self._headers(False), timeout=15)
            root = json.loads(r.text or "{}")
            data = str(root.get("data") or "")
            if not data:
                return {}
            return json.loads(_aes_cbc_dec(data, self.b, self.c) or "{}")
        except Exception:
            return {}

    def to_vod(self, o):
        if not isinstance(o, dict):
            return {}
        return {"vod_id": str(o.get("vod_id") or ""),
                "vod_name": str(o.get("vod_name") or ""),
                "vod_pic": str(o.get("vod_pic") or ""),
                "vod_remarks": str(o.get("vod_remarks") or "")}

    def homeContent(self, filter):
        cats, fts = [], {}
        try:
            for t in self.a.get("type_list") or []:
                if not isinstance(t, dict):
                    continue
                name = str(t.get("type_name") or "")
                if name in ("伦理", "福利", "小影院"):
                    continue
                tid = str(t.get("type_id") or "")
                cats.append({"type_id": tid, "type_name": name})
                fl = []
                for f in t.get("filter_type_list") or []:
                    if not isinstance(f, dict):
                        continue
                    lst = f.get("list") or []
                    if not lst or len(lst) == 0:
                        continue
                    fname = str(f.get("name") or "")
                    if fname not in ("class", "area", "lang", "year", "sort"):
                        continue
                    fl.append({"key": "by" if fname == "sort" else fname,
                               "name": fname,
                               "value": [{"n": s, "v": s} for s in lst]})
                if fl:
                    fts[tid] = fl
        except Exception:
            pass
        return {"class": cats, "filters": fts, "list": []}

    def homeVideoContent(self):
        lst = []
        for it in self.a.get("recommend_list") or []:
            lst.append(self.to_vod(it))
        return {"list": lst}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 90, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            body = {"type_id": str(tid), "page": pg}
            ex = extend or {}
            for k in ("class", "lang", "area", "year"):
                v = str(ex.get(k) or "").strip()
                if v:
                    body[k] = v
            if ex.get("by"):
                body["sort"] = str(ex["by"])
            j = self.post_json(f"/qijiappapi.index/typeFilterVodList?page={pg}",
                               json.dumps(body, ensure_ascii=False))
            lst = [self.to_vod(o) for o in j.get("recommend_list") or []]
            result["list"] = lst
            result["page"] = int(pg) if pg.isdigit() else 1
            result["pagecount"] = 9999
            result["total"] = 999999
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            j = self.post_json("/qijiappapi.index/vodDetail",
                               json.dumps({"vod_id": vid}))
            v = j.get("vod") or {}
            if not isinstance(v, dict):
                return {"list": []}
            froms, urls = [], []
            for pl in j.get("vod_play_list") or []:
                if not isinstance(pl, dict):
                    continue
                pinfo = pl.get("player_info") or {}
                show = str(pinfo.get("show") or "")
                parse_api = str(pinfo.get("parse") or "")
                eps = []
                for u in pl.get("urls") or []:
                    if not isinstance(u, dict):
                        continue
                    name = str(u.get("name") or "")
                    url = str(u.get("url") or "")
                    papi = str(u.get("parse_api_url") or "")
                    token = str(u.get("token") or "")
                    nid = str(u.get("nid") or "")
                    if re.match(r"^https?://.*", papi):
                        play = f"{papi}|{v.get('vod_name') or ''}|{nid}"
                    else:
                        enc = _aes_cbc_enc(url, self.b, self.c)
                        play = (f"parse_api={parse_api}&url={enc}&token={token}"
                                f"|{v.get('vod_name') or ''}|{nid}")
                    eps.append(f"{name}${play}")
                if eps:
                    froms.append(show)
                    urls.append("#".join(eps))
            vod = {"vod_id": vid,
                   "vod_name": str(v.get("vod_name") or ""),
                   "vod_pic": str(v.get("vod_pic") or ""),
                   "vod_remarks": str(v.get("vod_remarks") or ""),
                   "vod_content": str(v.get("vod_content") or ""),
                   "vod_actor": str(v.get("vod_actor") or ""),
                   "vod_director": str(v.get("vod_director") or "")}
            if froms:
                vod["vod_play_from"] = "$$$".join(froms)
                vod["vod_play_url"] = "$$$".join(urls)
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            pid = (playId or "").strip()
            if not pid:
                return {"parse": 0, "url": "", "header": {}, "error": "播放参数为空"}
            parts = pid.split("|")
            if len(parts) == 4:
                parts = [parts[0], parts[2], parts[3]]
            p0 = parts[0]
            hdr = {"User-Agent": UA_PC}
            # 1. 直接 http 解析 / 直链
            if re.match(r"^https?://.*", p0):
                if "?url=" in p0 or "?key=" in p0:
                    try:
                        j = json.loads(requests.get(p0, headers=hdr, timeout=15).text or "{}")
                        return {"parse": 0, "url": str(j.get("url") or ""), "header": hdr}
                    except Exception:
                        return {"parse": 0, "url": "", "header": hdr}
                if MEDIA_RE.match(p0):
                    return {"parse": 0, "url": p0, "header": hdr}
                if "?url=" not in p0 and "?key=" not in p0:
                    return {"parse": 0, "url": p0, "header": hdr}
            # 2. 含 parse_api= 的加密参数
            if "?url=" in p0 or "?key=" in p0 or "html" in p0:
                m = RE_URL.search(p0)
                if m:
                    try:
                        dec = _aes_cbc_dec(m.group(2), self.b, self.c)
                        p0 = p0[:m.start(2)] + dec + p0[m.end(2):]
                    except Exception:
                        pass
                m = RE_PARSE.search(p0)
                if m:
                    api = m.group(2)
                    try:
                        j = json.loads(requests.get(api, headers=hdr, timeout=15).text or "{}")
                        if isinstance(j, dict) and isinstance(j.get("data"), dict) and j["data"].get("url"):
                            return {"parse": 0, "url": str(j["data"]["url"]), "header": hdr}
                        if isinstance(j, dict) and j.get("url"):
                            return {"parse": 0, "url": str(j["url"]), "header": hdr}
                    except Exception:
                        pass
                    return {"parse": 0, "url": p0, "header": hdr}
            # 3. 走 vodParse
            m = RE_URL.search(p0)
            if m:
                p0 = p0[:m.start(2)] + quote(m.group(2), safe="") + p0[m.end(2):]
            ts = str(int(time.time()))
            h2 = self._headers(False)
            h2.update({"Connection": "Keep-Alive",
                       "Content-Type": "application/x-www-form-urlencoded",
                       "app-api-verify-time": ts,
                       "app-api-verify-sign": _aes_cbc_enc(ts, self.b, self.c)})
            try:
                r = requests.post(f"{self.host}/api.php/qijiappapi.index/vodParse",
                                  data=p0, headers=h2, timeout=15)
                root = json.loads(r.text or "{}")
                data = str(root.get("data") or "")
                mid = json.loads(_aes_cbc_dec(data, self.b, self.c) or "{}")
                jstr = mid.get("json")
                if isinstance(jstr, str):
                    out = json.loads(jstr)
                elif isinstance(jstr, dict):
                    out = jstr
                else:
                    out = {}
                return {"parse": 0, "url": str(out.get("url") or ""), "header": hdr}
            except Exception:
                return {"parse": 0, "url": "", "header": hdr}
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
            body = {"type_id": 0, "keywords": key, "page": int(pg)}
            j = self.post_json(f"/qijiappapi.index/{self.g}",
                               json.dumps(body, ensure_ascii=False))
            result["list"] = [self.to_vod(o) for o in j.get("search_list") or []]
            result["page"] = int(pg)
            result["pagecount"] = 9999
            result["total"] = 999999
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
