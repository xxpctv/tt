# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   曼波动漫 (AppGet)
# 协议: 请求体 JSON, 响应 data 字段 AES-CBC/PKCS5 加密(Base64), key/iv 来自 ext datakey/dataiv
# ext: {"host":"https://...","datakey":"...","dataiv":"...","init":"V119","ua":"okhttp/3.10.0"}
#      或 "host|key[|iv[|init[|ua]]]"; host 可为 .txt/.json 配置地址(自动拉取并追加 /api.php/getappapi)
# 说明: 完整复刻; 若站点开启搜索验证码(config.system_search_verify_status), 搜索返回提示.

from base.spider import Spider
import requests
import re
import json
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

DEFAULT_UA = "okhttp/3.10.0"
PLAY_UA = "Dalvik/2.1.0 (Linux; U; Android 14; Build/SKQ1.231004.001)"
CFG_RE = re.compile(r"^https?://.*\.(txt|json)$", re.I)


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


def _aes_cbc_enc(text, key, iv):
    pad = 16 - len(text.encode()) % 16
    data = text.encode() + bytes([pad]) * pad
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()),
                    backend=default_backend())
    enc = cipher.encryptor().update(data) + cipher.encryptor().finalize()
    return base64.b64encode(enc).decode()


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.api = ""
        self.key = ""
        self.iv = ""
        self.ua = DEFAULT_UA
        self.config = {}
        self.type_list = []
        self.verify = False

    def getName(self):
        return "曼波动漫"

    def init(self, extend=""):
        try:
            raw = (extend or "").strip()
            j = {}
            if raw.startswith("{"):
                j = json.loads(raw)
            elif "|" in raw:
                parts = [p.strip() for p in raw.split("|") if p.strip()]
                if len(parts) >= 2:
                    j = {"host": parts[0], "datakey": parts[1], "dataiv": parts[1]}
                    if len(parts) > 2:
                        v = parts[2]
                        if re.match(r"(?i)^V\d+$", v) or v.lower().startswith("init"):
                            j["init"] = v
                        elif len(v) in (16, 32):
                            j["dataiv"] = v
                            if len(parts) > 3 and re.match(r"(?i)^V\d+$", parts[3]):
                                j["init"] = "init" + parts[3].lower().lstrip("v") if not parts[3].lower().startswith("init") else parts[3]
                    if len(parts) > 2 and "okhttp" in parts[2].lower():
                        j["ua"] = parts[2]
            host = str(j.get("host") or j.get("url") or j.get("site") or "").strip()
            key = str(j.get("datakey") or j.get("dataKey") or j.get("key") or "").strip()
            if not host or not key:
                return
            iv = str(j.get("dataiv") or j.get("dataIv") or "").strip() or key
            self.key = key
            self.iv = iv
            self.ua = str(j.get("ua") or DEFAULT_UA)
            init_suffix = str(j.get("init") or "V119")
            if not init_suffix.lower().startswith("init"):
                init_suffix = "init" + init_suffix
            if CFG_RE.match(host):
                try:
                    r = requests.get(host, headers={"User-Agent": self.ua}, timeout=15)
                    host = (r.text or "").strip().rstrip("/+")
                except Exception:
                    return
            host = host.rstrip("/+")
            self.api = host + "/api.php/getappapi"
            self._init_config(init_suffix)
        except Exception:
            pass

    def _init_config(self, init_suffix):
        try:
            r = requests.get(f"{self.api}.index/{init_suffix}",
                             headers={"User-Agent": self.ua}, timeout=15)
            root = json.loads(r.text or "{}")
            cfg = json.loads(_aes_cbc_dec(root.get("data") or "", self.key, self.iv) or "{}")
            self.config = cfg
            self.type_list = cfg.get("type_list") or []
            c = cfg.get("config") or {}
            self.verify = bool(c.get("system_search_verify_status"))
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _post(self, path, params):
        try:
            r = requests.post(self.api + path, data=params,
                              headers={"User-Agent": self.ua}, timeout=15)
            root = json.loads(r.text or "{}")
            data = root.get("data")
            if data is None or data == "":
                return root
            return json.loads(_aes_cbc_dec(str(data), self.key, self.iv) or "{}")
        except Exception:
            return {}

    def _vod(self, it):
        return {"vod_id": str(it.get("vod_id") or ""),
                "vod_name": str(it.get("vod_name") or ""),
                "vod_pic": str(it.get("vod_pic") or ""),
                "vod_remarks": str(it.get("vod_remarks") or "")}

    def homeContent(self, filter):
        cats, fts = [], {}
        for t in self.type_list:
            name = str(t.get("type_name") or "")
            if not name or name == "全部" or name == "QQ" or "企鹅群" in name:
                continue
            tid = str(t.get("type_id") or "")
            cats.append({"type_id": tid, "type_name": name})
            fl = []
            for f in t.get("filter_type_list") or []:
                vals = f.get("list") or []
                if not vals:
                    continue
                key = f.get("name") or ""
                if key == "排序":
                    key = "by"
                fl.append({"key": key, "name": f.get("name") or key,
                           "value": [{"n": v, "v": v} for v in vals]})
            if fl:
                fts[tid] = fl
        return {"class": cats, "filters": fts, "list": []}

    def homeVideoContent(self):
        lst = []
        for t in self.type_list:
            for it in t.get("recommend_list") or []:
                lst.append(self._vod(it))
        return {"list": lst}

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 90, "total": 0}
        try:
            pg = str(pg) if str(pg).strip().isdigit() else "1"
            ex = extend or {}
            body = {"area": str(ex.get("area") or "全部"),
                    "year": str(ex.get("year") or "全部"),
                    "type_id": str(tid), "page": pg,
                    "sort": str(ex.get("by") or ex.get("sort") or "最新"),
                    "lang": str(ex.get("lang") or "全部"),
                    "class": str(ex.get("class") or "全部")}
            j = self._post(".index/typeFilterVodList", body)
            lst = [self._vod(it) for it in j.get("recommend_list") or []]
            result["list"] = lst
            n = int(pg) if pg.isdigit() else 1
            result["page"] = n
            result["pagecount"] = 9999
            result["total"] = 999999
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0])
            body = {"vod_id": vid}
            j = None
            for ep in ("vodDetail", "vodDetail2"):
                try:
                    j = self._post(f".index/{ep}", body)
                    if j:
                        break
                except Exception:
                    continue
            if not j:
                return {"list": []}
            v = j.get("vod") or {}
            play_from, play_url = [], []
            for pl in j.get("vod_play_list") or []:
                pinfo = pl.get("player_info") or {}
                show = str(pinfo.get("show") or "")
                if "防走丢" in show or "群" in show:
                    show = f"{len(play_from) + 1}线"
                elif "官网" in show:
                    show = f"{len(play_from) + 1}线"
                parse = str(pinfo.get("parse") or "")
                ptype = str(pinfo.get("parse_type") or "")
                pptype = str(pinfo.get("player_parse_type") or "")
                eps = []
                for u in pl.get("urls") or []:
                    eps.append(f"{u.get('name')}${parse},{u.get('url')},{'token+' + str(u.get('token') or '')},{pptype},{ptype}")
                if eps:
                    play_from.append(show)
                    play_url.append("#".join(eps))
            vod = {"vod_id": vid,
                   "vod_name": str(v.get("vod_name") or ""),
                   "vod_pic": str(v.get("vod_pic") or ""),
                   "vod_actor": str(v.get("vod_actor") or "").replace("演员", ""),
                   "vod_director": str(v.get("vod_director") or "").replace("导演", ""),
                   "vod_content": str(v.get("vod_content") or ""),
                   "vod_year": str(v.get("vod_year") or "") + "年",
                   "vod_area": str(v.get("vod_area") or ""),
                   "vod_remarks": f"时间:{v.get('vod_remarks') or ''} 语言:{v.get('vod_lang') or ''}"}
            if play_from:
                vod["vod_play_from"] = "$$$".join(play_from)
                vod["vod_play_url"] = "$$$".join(play_url)
        except Exception:
            pass
        return {"list": [vod] if vod else []}

    def playerContent(self, flag, playId, vipFlags):
        try:
            parts = str(playId or "").split(",", 5)
            if len(parts) < 2:
                return {"parse": 0, "url": "", "header": {}, "error": "播放参数错误"}
            parse_api = parts[0]
            url = parts[1]
            token = str(parts[2] if len(parts) > 2 else "").replace("token+", "")
            pptype = str(parts[3] if len(parts) > 3 else "1")
            ptype = str(parts[4] if len(parts) > 4 else "1")
            header = {"User-Agent": PLAY_UA}
            if ptype == "0":
                return {"parse": 0, "url": url, "header": header}
            if ptype == "2":
                return {"parse": 1, "url": url, "header": header}
            if pptype == "2":
                try:
                    r = requests.get(parse_api + url, headers=self.headers(), timeout=15)
                    j = json.loads(r.text or "{}")
                    return {"parse": 0, "url": str(j.get("url") or ""), "header": header}
                except Exception:
                    return {"parse": 0, "url": "", "header": header}
            j = self._post(".index/vodParse",
                           {"parse_api": parse_api,
                            "url": _aes_cbc_enc(url, self.key, self.iv),
                            "token": token})
            u = (j.get("json") or {})
            if isinstance(u, str):
                u = json.loads(u or "{}")
            return {"parse": 0, "url": str((u or {}).get("url") or ""), "header": header}
        except Exception:
            return {"parse": 0, "url": "", "header": {}, "error": "播放解析失败"}

    def headers(self):
        return {"User-Agent": self.ua}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            if self.verify:
                result["error"] = "本站搜索需验证码，独立版未接入 OCR，请换源或关闭搜索验证"
                return result
            j = self._post(".index/searchList",
                           {"keywords": key, "type_id": "0", "page": pg})
            lst = []
            for it in j.get("search_list") or []:
                lst.append({"vod_id": str(it.get("vod_id") or ""),
                            "vod_name": str(it.get("vod_name") or ""),
                            "vod_pic": str(it.get("vod_pic") or ""),
                            "vod_remarks": f"{it.get('vod_year') or ''} {it.get('vod_class') or ''}"})
            result["list"] = lst
            result["page"] = pg
            result["pagecount"] = 9999
            result["total"] = 999999
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
