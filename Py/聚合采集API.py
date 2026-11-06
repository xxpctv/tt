# -*- coding: utf-8 -*-
# 专属全网聚合 Python版
# 适配常见 Cat/TVBox Python Spider
#本地py适配
#
# 【7 个"本地过滤"源说明】
# 下面这 7 个站禁用了关键词搜索：接口一律回 "暂不支持搜索"（茅台回 code:1002），
# 网页搜索页也是 404/403，只能拉最新列表在本地按 片名/别名/导演/演员 筛
# （见 local_filter_hosts、local_filter_pages）。它们的库都在 12~15 万条 / 6000+ 页，
# 每源只翻 2 页（40 条），所以只覆盖"最新入库"，老剧搜不到，这是站点限制不是代码问题。
#   s7   OK       api.okzyw.net        total 125,485 / 6,275 页
#   s11  无水印    api.wsyzy.net        total 127,738 / 6,387 页
#   s16  牛牛      api.niuniuzy.me      total 125,550 / 6,278 页
#   s17  鸭鸭      cj.yayazy.net        total 123,593 / 6,180 页
#   s20  索尼      suoniapi.com         total 148,434 / 7,422 页
#   s25  快车      caiji.kuaichezy.org  total 126,947 / 6,348 页
#   s44  茅台      caiji.maotaizy.cc    total 152,074 / 7,604 页

import json
import re
import socket
import ssl
import requests
import base64
from urllib.parse import urlsplit, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from base.spider import Spider

try:
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass


class Spider(Spider):
    # 被按 SNI 阻断、需要走无 SNI 通道的站点（只对这些域名兜底，避免拖慢首页）
    no_sni_hosts = ('api.1080zyku.com', 'cj.rycjapi.com')
    # 记录各域名下次该从哪个节点开始（这些站按单节点限流）
    _ip_cursor = {}
    # 服务器强制要求 SNI、直连必被阻断的站点：借 App 自带的 OkHttp 出去
    # （走 Java 网络栈，能协商 h2/h3，也会吃系统代理），不做本机代理兜底
    java_hosts = ('ikunzyapi.com',)
    _java_client = [None]
    # 这些站的搜索只认 ac=list，ac=detail 会忽略 wd 返回最新列表
    search_list_hosts = ('api.1080zyku.com',)

    sources = {
        's1': {'name': '芒果', 'api': 'https://caiji.mgzyapi.com/api.php/provide/vod'},
        's2': {'name': '厂长', 'api': 'https://api.changzhang.tv/api.php/provide/vod'},
        's3': {'name': '母鸡', 'api': 'https://mujiziyuan00.com/api.php/provide/vod'},
        's4': {'name': '天涯', 'api': 'https://tyyszyapi.com/api.php/provide/vod'},
        's5': {'name': '天涯2', 'api': 'https://ty.tyyszy5.com/api.php/provide/vod/'},
        's6': {'name': '360', 'api': 'https://360zyzz.com/api.php/provide/vod'},
        's7': {'name': 'OK', 'api': 'https://api.okzyw.net/api.php/provide/vod'},
        's8': {'name': '最大', 'api': 'https://zuidazy.co/api.php/provide/vod'},
        's9': {'name': '最大2', 'api': 'https://api.zuidapi.com/api.php/provide/vod'},
        's10': {'name': '西瓜', 'api': 'https://caiji.xgzyapi.com/api.php/provide/vod'},
        's11': {'name': '无水印', 'api': 'https://api.wsyzy.net/api.php/provide/vod'},
        's12': {'name': '爱奇艺', 'api': 'https://iqiyizyapi.com/api.php/provide/vod'},
        's13': {'name': '非凡', 'api': 'https://api.ffzyapi.com/api.php/provide/vod'},
        's14': {'name': '非凡2', 'api': 'https://cj.ffzyapi.com/api.php/provide/vod'},
        's15': {'name': '非凡3', 'api': 'https://ffzy.tv/api.php/provide/vod/'},
        's16': {'name': '牛牛', 'api': 'https://api.niuniuzy.me/api.php/provide/vod'},
        's17': {'name': '鸭鸭', 'api': 'https://cj.yayazy.net/api.php/provide/vod'},
        's18': {'name': '天堂', 'api': 'https://caiji.dyttzyapi.com/api.php/provide/vod'},
        's19': {'name': '虎牙', 'api': 'https://www.huyaapi.com/api.php/provide/vod'},
        's20': {'name': '索尼', 'api': 'https://suoniapi.com/api.php/provide/vod'},
        's21': {'name': '极速', 'api': 'https://jszyapi.com/api.php/provide/vod'},
        's22': {'name': '暴风', 'api': 'https://bfzy2.tv/api.php/provide/vod'},
        's23': {'name': '暴风2', 'api': 'https://bfzyapi.com/api.php/provide/vod/'},
        's24': {'name': '豪华', 'api': 'https://hhzyapi.com/api.php/provide/vod'},
        's25': {'name': '快车', 'api': 'https://caiji.kuaichezy.org/api.php/provide/vod'},
        's26': {'name': '速播', 'api': 'https://subocj.com/api.php/provide/vod'},
        's27': {'name': '速播2', 'api': 'https://subocaiji.com/api.php/provide/vod'},
        's28': {'name': '新浪', 'api': 'https://api.xinlangapi.com/xinlangapi.php/provide/vod'},
        's29': {'name': '光速', 'api': 'https://api.guangsuapi.com/api.php/provide/vod'},
        's30': {'name': '无尽', 'api': 'https://api.wujinapi.me/api.php/provide/vod'},
        's31': {'name': '无尽2', 'api': 'https://api.wujinapi.cc/api.php/provide/vod'},
        's32': {'name': '魔都', 'api': 'https://www.mdzyapi.com/api.php/provide/vod'},
        's33': {'name': '金鹰', 'api': 'https://jyzyapi.com/provide/vod'},
        's34': {'name': '金鹰2', 'api': 'https://jinyingzy.com/api.php/provide/vod'},
        's35': {'name': '量子', 'api': 'https://cj.lziapi.com/api.php/provide/vod'},
        's36': {'name': '百度', 'api': 'https://api.apibdzy.com/api.php/provide/vod'},
        's37': {'name': '闪电', 'api': 'https://xsd.sdzyapi.com/api.php/provide/vod'},
        's38': {'name': '闪电2', 'api': 'https://sdzyapi.com/api.php/provide/vod'},
        's39': {'name': 'U酷', 'api': 'https://api.ukuapi88.com/api.php/provide/vod'},
        's40': {'name': '樱花', 'api': 'https://m3u8.apiyhzy.com/api.php/provide/vod'},
        's41': {'name': '电影天堂', 'api': 'http://caiji.dyttzyapi.com/api.php/provide/vod/from/dyttm3u8/at/json'},
        's42': {'name': '1080资源', 'api': 'https://api.1080zyku.com/inc/api_mac10.php'},
        's43': {'name': '红牛', 'api': 'https://www.hongniuzy2.com/api.php/provide/vod/'},
        's44': {'name': '茅台', 'api': 'https://caiji.maotaizy.cc/api.php/provide/vod/'},
        's45': {'name': '如意影视', 'api': 'https://cj.rycjapi.com/api.php/provide/vod/'},
        's46': {'name': '飘零', 'api': 'https://p2100.net/api.php/provide/vod'},
        's47': {'name': '大众资源', 'api': 'https://cdn.dzzyapi.com/api.php/provide/vod/'},
        's48': {'name': '155资源', 'api': 'https://155api.com/api.php/provide/vod'},
        's49': {'name': 'ikun', 'api': 'https://ikunzyapi.com/api.php/provide/vod'},
    }

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    def getName(self):
        return "采集聚合"

    def init(self, extend=""):
        pass

    def fetch(self, url, timeout=8):
        host = urlsplit(url).hostname or ''

        # 这类站服务器要按 SNI 选证书，CPython 的 TLS 直连一定被掐，
        # 只能借 App 自带的 OkHttp（Java 网络栈）出去
        if host in self.java_hosts:
            text = self._java_fetch_text(url, timeout)
            return text if text and text.strip() else ''

        text = ''
        try:
            r = requests.get(
                url,
                headers=self.headers,
                timeout=timeout,
                verify=False
            )
            text = r.text
        except Exception:
            text = ''
        if text and text.strip():
            return text
        # 带 SNI 被阻断时，有时是被 RST、有时直接给个空 200，
        # 所以空结果也算失败；只有确知被阻断的站点才走无 SNI 通道
        if host in self.no_sni_hosts:
            return self.fetch_no_sni(url, timeout if timeout >= 8 else 8)
        return ''

    def _get_java_client(self):
        if self._java_client[0] is not None:
            return self._java_client[0] or None
        try:
            from java import jclass
            Builder = jclass("okhttp3.OkHttpClient$Builder")
            TimeUnit = jclass("java.util.concurrent.TimeUnit")
            b = Builder()
            b.followRedirects(True)
            b.followSslRedirects(True)
            b.connectTimeout(10, TimeUnit.SECONDS)
            b.readTimeout(20, TimeUnit.SECONDS)
            b.writeTimeout(10, TimeUnit.SECONDS)
            self._java_client[0] = b.build()
        except Exception:
            self._java_client[0] = False
        return self._java_client[0] or None

    def _java_fetch_text(self, url, timeout=8):
        """用 App 自带的 OkHttp 取一次 GET，拿不到返回空串。"""
        client = self._get_java_client()
        if client is None:
            return ''
        try:
            from java import jclass
            ReqBuilder = jclass("okhttp3.Request$Builder")
            rb = ReqBuilder()
            rb.url(url)
            try:
                rb.header('User-Agent', self.headers.get('User-Agent', 'Mozilla/5.0'))
                rb.header('Accept', '*/*')
            except Exception:
                pass
            resp = client.newCall(rb.build()).execute()
            code = 0
            try:
                code = int(resp.code())
            except Exception:
                pass
            body = b''
            try:
                bd = resp.body()
                if bd is not None:
                    body = bytes(bd.bytes())
            except Exception:
                pass
            try:
                resp.close()
            except Exception:
                pass
            if code >= 400 or not body:
                return ''
            return body.decode('utf-8', 'ignore')
        except Exception:
            return ''

    def fetch_no_sni(self, url, timeout=8):
        """不发 SNI、直连 IP、只靠 Host 头路由。

        部分采集站对 TLS ClientHello 里的域名做阻断：带 SNI 立刻被 RST，
        去掉 SNI 后同一台主机能正常返回 JSON。requests 无法关闭 SNI，
        所以这里用 socket + ssl 自己做一次。

        这类站还按单个节点限流：同一 IP 连着打第二次会被拖到超时，
        换一个节点就立刻正常，所以每次调用都轮换起始节点。
        """
        parts = urlsplit(url)
        host = parts.hostname
        if not host:
            return ""

        port = parts.port or (443 if parts.scheme == 'https' else 80)
        path = (parts.path or '/') + (('?' + parts.query) if parts.query else '')

        ips = self._rotate_ips(host, port)
        if not ips:
            return ""

        for i, ip in enumerate(ips[:2]):
            text = self._no_sni_once(
                ip, host, port, path,
                timeout if i == 0 else max(3, timeout - 3)
            )
            if text and text.strip():
                return text
        return ""

    def _rotate_ips(self, host, port):
        try:
            ips = [ai[4][0] for ai in socket.getaddrinfo(host, port, socket.AF_INET)]
        except Exception:
            return []
        ips = [x for x in dict.fromkeys(ips) if x]
        if not ips:
            return []
        i = self._ip_cursor.get(host, 0) % len(ips)
        self._ip_cursor[host] = i + 1
        return ips[i:] + ips[:i]

    def _no_sni_once(self, ip, host, port, path, timeout):
        sock = None
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            raw = socket.create_connection((ip, port), timeout=timeout)
            sock = ctx.wrap_socket(raw)   # 不传 server_hostname -> 不发 SNI

            req = (
                'GET %s HTTP/1.1\r\n'
                'Host: %s\r\n'
                'User-Agent: %s\r\n'
                'Accept: */*\r\n'
                'Connection: close\r\n'
                '\r\n'
                % (path, host, self.headers.get('User-Agent', 'Mozilla/5.0'))
            )
            sock.sendall(req.encode('utf-8'))

            buf = b''
            while len(buf) < 4000000:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk

            head, sep, body = buf.partition(b'\r\n\r\n')
            if not sep:
                return ""
            if b'transfer-encoding: chunked' in head.lower():
                body = self._dechunk(body)
            return body.decode('utf-8', 'ignore')
        except Exception:
            return ""
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    @staticmethod
    def _dechunk(raw):
        out = []
        pos = 0
        while pos < len(raw):
            eol = raw.find(b'\r\n', pos)
            if eol < 0:
                break
            try:
                size = int(raw[pos:eol].split(b';')[0], 16)
            except Exception:
                break
            if size <= 0:
                break
            start = eol + 2
            out.append(raw[start:start + size])
            pos = start + size + 2
        return b''.join(out)

    def clean_item(self, item, source_key, source_name, is_detail=False):
        item = dict(item)

        if not is_detail:
            item["vod_id"] = f"{source_key}@@{item.get('vod_id', '')}"

        remarks = item.get("vod_remarks", "")
        item["vod_remarks"] = f"{source_name} | {remarks}"

        if item.get("vod_play_from"):
            froms = item["vod_play_from"].split("$$$")
            froms = [f"{source_name}-{x}" for x in froms]
            item["vod_play_from"] = "$$$".join(froms)

        item.pop("vod_down_from", None)
        item.pop("vod_down_url", None)

        return item

    def homeContent(self, filter):
        classes = []
        filters = {}

        def load_class(key, source):
            url = f"{source['api']}?ac=list"
            html = self.fetch(url, 3)

            try:
                data = json.loads(html)
            except:
                data = {}

            vals = [{"n": "全部(最新)", "v": ""}]

            for c in data.get("class", []):
                vals.append({
                    "n": c.get("type_name", ""),
                    "v": c.get("type_id", "")
                })

            return key, vals

        with ThreadPoolExecutor(max_workers=32) as executor:
            futures = []

            for key, source in self.sources.items():
                classes.append({
                    "type_id": key,
                    "type_name": source["name"]
                })

                futures.append(executor.submit(load_class, key, source))

            for future in as_completed(futures):
                try:
                    key, vals = future.result()

                    filters[key] = [{
                        "key": "cateId",
                        "name": "分类",
                        "value": vals
                    }]
                except:
                    pass

        return {
            "class": classes,
            "filters": filters,
            "list": []
        }

    def categoryContent(self, tid, pg, filter, extend):
        if tid not in self.sources:
            return {"list": []}

        source = self.sources[tid]

        cate_id = ""
        if isinstance(extend, dict):
            cate_id = extend.get("cateId", "")

        url = f"{source['api']}?ac=detail&pg={pg}"

        if cate_id:
            url += f"&t={cate_id}"

        html = self.fetch(url)

        try:
            data = json.loads(html)
        except:
            data = {}

        result = []

        for item in data.get("list", []):
            result.append(
                self.clean_item(
                    item,
                    tid,
                    source["name"],
                    False
                )
            )

        return {
            "list": result,
            "page": data.get("page", pg),
            "pagecount": data.get("pagecount", 1),
            "limit": data.get("limit", 20),
            "total": data.get("total", len(result))
        }

    def detailContent(self, ids):
        if isinstance(ids, list):
            ids = ids[0]

        if "@@" not in ids:
            return {"list": []}

        source_key, real_id = ids.split("@@", 1)

        if source_key not in self.sources:
            return {"list": []}

        source = self.sources[source_key]

        url = f"{source['api']}?ac=detail&ids={real_id}"

        html = self.fetch(url)

        try:
            data = json.loads(html)
        except:
            data = {}

        result = []

        ad = "✈️关注裤佬Telegram频道 https://t.me/stymei"

        for item in data.get("list", []):
            cleaned = self.clean_item(
                item,
                source_key,
                source["name"],
                True
            )

            cleaned["vod_id"] = ids

            # 简介末尾追加引流文案
            content = cleaned.get("vod_content", "") or ""
            if ad not in content:
                cleaned["vod_content"] = f"{content}\n\n{ad}".strip()

            result.append(cleaned)

        return {"list": result}

    @staticmethod
    def _filter_search(vods, key):
        """服务端会按简介拆词搜，这里只认片名/别名/导演/演员的完整子串，
        关键词不拆，命中任一字段才留，避免搜出一堆无关结果。"""
        kw = re.sub(r"\s+", "", str(key or "")).lower()

        if not kw:
            return vods

        out = []

        for v in vods or []:
            for field in ("vod_name", "vod_sub", "vod_actor", "vod_director"):
                if kw in re.sub(r"\s+", "", str(v.get(field, "") or "")).lower():
                    out.append(v)
                    break

        return out

    # 搜索接口禁了 wd 的站里，网页搜索页还能用的这几个：走网页搜 id 再回 API 取详情
    # 键是 API 域名，值是网页搜索基址（同一套内容，挑能连上的那个）
    web_search_hosts = {
        'tyyszyapi.com': 'https://tyyszyapi.com',
        'tyyszy.com': 'https://tyyszyapi.com',
        'ty.tyyszy5.com': 'https://tyyszyapi.com',
        'xsd.sdzyapi.com': 'https://sdzyapi.com',
        'sdzyapi.com': 'https://sdzyapi.com',
    }
    # 搜索接口和网页都搜不了（"暂不支持搜索"/403）的站：改拉最新列表在本地筛
    local_filter_hosts = (
        'api.okzyw.net', 'api.wsyzy.net', 'api.niuniuzy.me',
        'cj.yayazy.net', 'suoniapi.com', 'caiji.kuaichezy.org',
        'caiji.maotaizy.cc',
    )
    # 每个源往下翻几页做本地筛（1 页 20 条）。这些站都在 12~15 万条 / 6000+ 页，
    # 翻多了没用还挤占线程池，只当"最新入库"补充
    local_filter_pages = 2

    def _web_search(self, source_key, source, base, keyword):
        """搜索接口禁了 wd 的站，用它的网页搜索页拿 vod_id，再回 API 批量取详情。"""
        try:
            html = self.fetch(
                "%s/index.php/vod/search.html?wd=%s" % (base, quote(keyword)), 6
            )
        except Exception:
            html = ""

        if not html:
            return []

        ids = []

        for m in re.finditer(r'detail/id/(\d+)\.html|voddetail/(\d+)\.html', html):
            vid = m.group(1) or m.group(2)
            if vid and vid not in ids:
                ids.append(vid)

        if not ids:
            return []

        ids = ids[:20]

        try:
            data = json.loads(
                self.fetch("%s?ac=detail&ids=%s" % (source["api"], ",".join(ids)), 8) or "{}"
            )
        except Exception:
            return []

        out = []

        for item in self._filter_search(data.get("list", []), keyword):
            out.append(self.clean_item(item, source_key, source["name"], False))

        return out

    def _local_filter_search(self, source_key, source, keyword):
        """这些站禁了 wd，只能往下翻最新列表，在本地按片名/别名/导演/演员筛。"""
        out = []
        seen = set()

        for pg in range(1, self.local_filter_pages + 1):
            try:
                data = json.loads(
                    self.fetch("%s?ac=detail&pg=%d" % (source["api"], pg), 6) or "{}"
                )
            except Exception:
                break

            items = data.get("list", [])

            if not items:
                break

            for item in self._filter_search(items, keyword):
                vid = str(item.get("vod_id", ""))
                if vid and vid in seen:
                    continue
                if vid:
                    seen.add(vid)
                out.append(self.clean_item(item, source_key, source["name"], False))

        return out

    def search_one(self, source_key, source, keyword, pg):
        host = urlsplit(source["api"]).hostname or ""

        try:
            pg_no = int(pg)
        except Exception:
            pg_no = 1

        # 网页搜索 / 本地列表过滤都只取首屏，没有真分页。pg>1 必须返回空，
        # 否则同一批结果会在第 2、3…页反复出现（同一条目看到 3 次就是这原因）
        if pg_no > 1 and (host in self.web_search_hosts or host in self.local_filter_hosts):
            return {"list": [], "pagecount": 1}

        base = self.web_search_hosts.get(host)
        if base:
            return {"list": self._web_search(source_key, source, base, keyword), "pagecount": 1}

        if host in self.local_filter_hosts:
            return {"list": self._local_filter_search(source_key, source, keyword), "pagecount": 1}

        # 这些站的 ac=detail 会无视 wd 直接吐最新列表，搜索得走 ac=list
        ac = "list" if host in self.search_list_hosts else "detail"

        url = f"{source['api']}?ac={ac}&wd={keyword}&pg={pg}"

        html = self.fetch(url, 6)

        try:
            data = json.loads(html)
        except:
            data = {}

        result = []

        for item in self._filter_search(data.get("list", []), keyword):
            result.append(
                self.clean_item(
                    item,
                    source_key,
                    source["name"],
                    False
                )
            )

        return {
            "list": result,
            "pagecount": data.get("pagecount", 1)
        }

    def searchContent(self, key, quick=False, pg=1):
        result = []
        max_page = 1

        with ThreadPoolExecutor(max_workers=32) as executor:
            futures = []

            for source_key, source in self.sources.items():
                futures.append(
                    executor.submit(
                        self.search_one,
                        source_key,
                        source,
                        key,
                        pg
                    )
                )

            for future in as_completed(futures):
                try:
                    data = future.result()

                    result.extend(data["list"])

                    if data["pagecount"] > max_page:
                        max_page = data["pagecount"]

                except:
                    pass

        return {
            "list": result,
            "page": pg,
            "pagecount": max_page,
            "limit": 40,
            "total": 9999
        }

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": self.headers
        }

    def localProxy(self, param):
        return [200, "text/plain", "ok"]


if __name__ == "__main__":
    Spider().run()