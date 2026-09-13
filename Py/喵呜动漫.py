# -*- coding: utf-8 -*-
# 兼容 OK影视/影视仓   喵呜动漫 (MiaoWu)
# 依赖: requests + cryptography（OK影视/影视仓 Python 引擎自带）

from base.spider import Spider
import requests
import base64
import json
import re
from urllib.parse import quote
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY_DATA = b"c55c019c59a9fbe196ef9fc7d2a0b351"   # 响应 data AES key (Java getBytes 即 ASCII)
KEY_DOH = b"6516c20a87257caa418c721caf6a8c12"    # DoH 域名 AES key
HEADERS = {"User-Agent": "Dart/3.5 (dart:io)", "content-type": "application/json"}


def _aes_decrypt(data_b64, key):
    raw = base64.b64decode(data_b64)
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    out = dec.update(raw) + dec.finalize()
    pad = out[-1] if out else 0
    if 0 < pad <= 16:
        out = out[:-pad]
    return out.decode("utf-8", "ignore")


def _norm_api(url):
    url = (url or "").strip()
    if url.endswith("/app/api"):
        return url + "/"
    if url.endswith("/app/api/"):
        return url
    if url.endswith("/"):
        return url + "app/api/"
    return url + "/app/api/"


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.api = ""
        self._doh_done = False

    def getName(self):
        return "喵呜动漫"

    def init(self, extend=""):
        if extend:
            try:
                s = extend.strip()
                if s.startswith("{"):
                    u = json.loads(s).get("url", "")
                    if u:
                        self.api = _norm_api(u)
                elif s.startswith("http"):
                    self.api = _norm_api(s)
            except Exception:
                pass
        self._resolve_doh()

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _resolve_doh(self):
        if self._doh_done:
            return
        self._doh_done = True
        try:
            r = requests.get("https://doh.pub/resolve?name=doh.catw.moe&type=txt",
                             headers=HEADERS, timeout=12)
            ans = r.json().get("Answer") or []
            if not ans:
                return
            data = ans[0].get("data", "")
            m = re.search(r'"(.*?)"', data)
            b64 = m.group(1) if m else data.strip().strip('"')
            host = _aes_decrypt(b64, KEY_DOH).strip()
            if host.startswith("http"):
                self.api = host.rstrip("/") + "/app/api/"
        except Exception:
            pass

    def _get_json(self, path):
        try:
            txt = requests.get(self.api + path, headers=HEADERS, timeout=15).text
        except Exception:
            return {}
        try:
            j = json.loads(txt)
        except Exception:
            return {}
        data = j.get("data")
        if isinstance(data, str) and len(data) > 16 and not data.lstrip().startswith(("{", "[")):
            try:
                j = json.loads(_aes_decrypt(data, KEY_DATA))
            except Exception:
                pass
        return j

    @staticmethod
    def _parse_vods(j):
        out = []
        arr = j.get("filter_vods")
        if arr is None:
            arr = j.get("search_full")
        for it in arr or []:
            vid = str(it.get("id") if it.get("id") is not None else it.get("vod_id") or "").strip()
            name = str(it.get("vod_name") or "").strip()
            if not vid or not name or vid == "null":
                continue
            out.append({"vod_id": vid, "vod_name": name,
                        "vod_pic": it.get("vod_pic") or "",
                        "vod_remarks": it.get("vod_remarks") or ""})
        return out

    def homeContent(self, filter):
        result = {"class": [], "filters": {}}
        try:
            j = self._get_json("config?platform=android")
            for it in j.get("ac_vod_type") or []:
                tid = str(it.get("type_id") or "").strip()
                tname = str(it.get("type_name") or "").strip()
                if not tid or not tname or tid == "null":
                    continue
                result["class"].append({"type_id": tid, "type_name": tname})
                ext = it.get("type_extend") or {}
                fs = []
                for key, label in (("class", "类型"), ("year", "年份")):
                    vals = ext.get(key) or ""
                    if not vals or "请" in vals or "建议" in vals or len(vals) > 80:
                        continue
                    vlist = [v.strip() for v in vals.split(",") if v.strip()]
                    if len(vlist) > 1:
                        fs.append({"key": key, "name": label,
                                   "value": [{"n": "全部", "v": ""}] +
                                            [{"n": v, "v": v} for v in vlist]})
                if fs:
                    result["filters"][tid] = fs
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.categoryContent("", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": pg, "pagecount": 1, "limit": 12, "total": 0}
        try:
            pg = int(pg) if str(pg).strip().isdigit() else 1
            j = self._get_json(f"content/filter?page={pg}&sort=0&type={quote(str(tid))}")
            result["list"] = self._parse_vods(j)
            result["page"] = pg
            nxt = pg if len(result["list"]) < 12 else pg + 1
            result["pagecount"] = max(1, nxt)
            result["total"] = nxt * 12
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod = {}
        try:
            vid = str(ids[0]).strip()
            if not vid:
                return {"list": []}
            j = self._get_json("vod/" + quote(vid))
            vod = {
                "vod_id": vid,
                "vod_name": j.get("vod_name") or "",
                "vod_pic": j.get("vod_pic") or "",
                "vod_year": j.get("vod_year") or "",
                "vod_content": j.get("vod_content") or "",
                "vod_actor": j.get("vod_author") or "",
                "vod_remarks": j.get("vod_remarks") or "",
            }
            froms, urls = [], []
            for idx, pd in enumerate(j.get("playerData") or []):
                name = str(pd.get("name") or "").strip()
                player = str(pd.get("player") or "").strip()
                vids = [str(v).strip() for v in (pd.get("vids") or []) if str(v).strip() and str(v).strip() != "null"]
                if not vids:
                    continue
                eps = []
                for i, v in enumerate(vids):
                    if "$" in v:
                        eps.append(f"{v}|||{player}")
                    else:
                        eps.append(f"第{i + 1}集${v}|||{player}")
                if not eps:
                    continue
                froms.append(name or f"线路{idx + 1}")
                urls.append("#".join(eps))
            vod["vod_play_from"] = "$$$".join(froms)
            vod["vod_play_url"] = "$$$".join(urls)
        except Exception:
            pass
        return {"list": [vod]}

    def playerContent(self, flag, playId, vipFlags):
        url = ""
        try:
            p = playId or ""
            player = ""
            if "|||" in p:
                url, player = p.split("|||", 1)
            else:
                url = p
            if "$" in url:
                url = url[url.rfind("$") + 1:]
            if "http" in url and "mwvod" not in url:
                return {"parse": 0, "url": url, "header": HEADERS}
            body = json.dumps({"vid": url, "player": player}, ensure_ascii=False)
            resp = requests.post(self.api + "vod/parse", data=body, headers=HEADERS, timeout=15)
            txt = resp.text
            try:
                j = json.loads(txt)
                data = j.get("data")
                if isinstance(data, str) and len(data) > 16 and not data.lstrip().startswith(("{", "[")):
                    j = json.loads(_aes_decrypt(data, KEY_DATA))
                url = j.get("play_url") or ""
            except Exception:
                pass
        except Exception:
            pass
        return {"parse": 0, "url": url, "header": HEADERS}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        result = {"list": []}
        try:
            key = str(key or "").strip()
            if not key:
                return result
            j = self._get_json("search/full?q=" + quote(key))
            result["list"] = self._parse_vods(j)
        except Exception:
            pass
        return result

    def localProxy(self, param):
        return [200, "video/mp4", [], ""]
