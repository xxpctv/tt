# -*- coding: utf-8 -*-
# ============================================================
# AjeoZB-DB.py — OK影视/TVBox Python 聚合蜘蛛
# 由 AjeoZB-DB.js 移植改造：
#   1) 完整保留 JS 版全部直播源与逻辑（url 文本源 m3u/txt/json 解析、
#      咪咕 302 签名中转、live_filter 动态过滤、本地搜索去重）
#   2) 新增 py 子源支持（type=3 + api）：importlib 动态加载子爬虫，
#      liveContent() 取频道、localProxy() 转发播放，解决 JS 引擎
#      无法加载 py 子源的问题（央卫直播 / 咕噜央视）
#   3) 修复 JS 版 type_id=name+'$'+url 在无 url 字段时退化成
#      "央卫直播$undefined" 的缺陷：py 版以源 name 为分类 id
# ============================================================

import os
import re
import sys
import json
import time
import hashlib
import threading
import importlib.util

from urllib.parse import urlparse, urljoin

try:
    import requests
except ImportError:
    requests = None
try:
    import urllib.request
    import ssl as _ssl
except ImportError:
    urllib = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()
CACHE_DIR = os.path.join(SCRIPT_DIR, 'cache')
MODULE_CACHE_DIR = os.path.join(CACHE_DIR, 'modules')
MODULE_CACHE_TTL = 3600          # py 子源缓存有效期（秒）
REQ_TIMEOUT = 8                  # 常规访问超时（秒）
SEARCH_TIMEOUT = 5               # 搜索冷启动超时
LIVE_FILTER_TIMEOUT = 2.5        # 直播源 host 探测超时

PIC_URL = 'https://d.kstore.dev/download/8043/BJ/bj-2.jpg'
DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

# ============================ 源列表 ============================
# 与 AjeoZB-DB.js LIVS_SOURCES 完全一致；type=3+api 为 py 子源
# 注意：py 子源 api 必须是完整 URL（云端或本地分发服务），OK影视 端只下载
#       AjeoZB-DB.py 单个文件执行，相对路径（如 ./Py/咕噜央视.py）在云端无效——
#       引擎不会去拉取 ./Py/ 下的子源文件。相对路径仅在子源与聚合器
#       同机同目录共存（本地文件系统模式）时有效。
# 云端部署：gitlink raw；本地 8899 调试可改回 http://192.168.1.160:8899/py/
LOCAL_PY_BASE = 'https://cdn09022024.gitlink.org.cn/api/v1/repos/ajeo/k1/raw/Py/'
LIVS_SOURCES = [
    {"name": "央卫直播", "type": 3, "api": LOCAL_PY_BASE + "央卫直播live-ysp.py"},
    {"key": "咕噜央视-海豚", "name": "咕噜央视", "type": 3, "api": LOCAL_PY_BASE + "咕噜央视.py"},
    {"name": "裤佬直播", "url": "https://gh-proxy.com/https://raw.githubusercontent.com/pyapk/1/refs/heads/main/zby"},
    {"name": "平台直播", "url": "http://47.120.41.246:8025/vip/jar/zb.php", "ua": "okhttp/3.12.13", "live_filter": True},
    {"name": "刚哥TV", "url": "https://gitee.com/yuan301/tv/raw/master/A/z_v.png"},
    {"name": "YTV", "url": "https://ytv1.ccwu.cc/output/live.m3u"},
    {"name": "俄罗斯TV", "url": "https://ilook.epg.one/5CM5SY98BF24PL/2"},
    {"name": "咪咕TV", "url": "http://zo.gt.tc/o/i/央视卫视js.txt"},
    {"name": "关注直播（大师）", "type": 0, "url": "https://cdn09022024.gitlink.org.cn/api/v1/repos/ajeo/k1/raw/my/sczb.txt"},
    {"name": "私藏音乐（大师）", "type": 0, "url": "https://cdn09022024.gitlink.org.cn/api/v1/repos/ajeo/k1/raw/my/scMV.txt"},
]

MIGU_HOST = 'migu.qq163gmail.eu.org'   # 咪咕直播中转入口 host


# ============================ 工具函数 ============================
def _ensure_dirs():
    try:
        os.makedirs(MODULE_CACHE_DIR, exist_ok=True)
    except Exception:
        pass


def http_get_text(url, headers=None, timeout=REQ_TIMEOUT):
    """通用 HTTP GET，返回 UTF-8 解码文本；requests 不可用时回退 urllib（标准库）。
    返回 None 表示失败。所有调用方（子源下载/url 源抓取）必须走本函数，
    统一强制 UTF-8，避免远端无 charset 时按 latin-1 解码导致中文乱码。"""
    hdrs = dict(headers or {})
    if 'User-Agent' not in hdrs:
        hdrs['User-Agent'] = DEFAULT_UA
    if requests is not None:
        try:
            resp = requests.get(url, timeout=timeout, headers=hdrs, verify=False)
            if resp.status_code != 200:
                return None
            if not resp.encoding or resp.encoding.lower() not in ('utf-8', 'utf8'):
                resp.encoding = 'utf-8'
            return resp.text
        except Exception:
            pass
    if urllib is not None:
        try:
            req = urllib.request.Request(url, headers=hdrs)
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                raw = r.read()
            try:
                return raw.decode('utf-8')
            except Exception:
                return raw.decode('utf-8', errors='replace')
        except Exception:
            pass
    return None


def extract_host_from_url(url):
    try:
        return urlparse(url).netloc
    except Exception:
        m = re.search(r'://([^/]+)', url or '')
        return m.group(1) if m else None


def try_decrypt_content(content, url):
    """按需扩展：JS 版无解密，保留占位（用于某些源返回加密文本时）"""
    return content


def resolve_py_path(path):
    """解析 py 子源路径，多级回退：
       1) 完整 URL 原样返回
       2) 绝对路径直接返回
       3) 相对路径依次尝试 SCRIPT_DIR/Py/x.py、SCRIPT_DIR/x.py、
          cwd/Py/x.py、cwd/x.py，最后在 SCRIPT_DIR 内按 basename 模糊匹配
    """
    if not path:
        return None
    if path.startswith(('http://', 'https://', 'ftp://')):
        return path
    if os.path.isabs(path):
        return path if os.path.isfile(path) else None
    base = os.path.basename(path.replace('\\', '/'))
    candidates = [
        os.path.join(SCRIPT_DIR, path),
        os.path.join(SCRIPT_DIR, path.lstrip('./.\\')),
        os.path.join(os.getcwd(), path),
        os.path.join(os.getcwd(), path.lstrip('./.\\')),
        os.path.join(SCRIPT_DIR, base),
        os.path.join(SCRIPT_DIR, 'Py', base),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # 最后兜底：SCRIPT_DIR 下按文件名模糊匹配（含子目录）
    for root, _dirs, files in os.walk(SCRIPT_DIR):
        for f in files:
            if f == base:
                return os.path.join(root, f)
        if root != SCRIPT_DIR and root.count(os.sep) - SCRIPT_DIR.count(os.sep) >= 2:
            break
    return candidates[0]


def load_py_module(api):
    """动态加载 py 子爬虫模块：
       远程 URL → 下载到缓存目录（TTL）再 importlib 加载
       本地路径 → 直接 importlib 加载
       返回 module 或 None
    """
    try:
        _ensure_dirs()
        fp = None
        if api.startswith(('http://', 'https://')):
            ck = hashlib.md5(api.encode()).hexdigest() + '.py'
            cf = os.path.join(MODULE_CACHE_DIR, ck)
            if os.path.isfile(cf) and (time.time() - os.path.getmtime(cf)) < MODULE_CACHE_TTL:
                fp = cf
            else:
                text = http_get_text(api, timeout=REQ_TIMEOUT)
                if text is None:
                    return None
                try:
                    with open(cf, 'w', encoding='utf-8') as f:
                        f.write(text)
                    fp = cf
                except Exception:
                    return None
        else:
            p = resolve_py_path(api)
            if not p or not os.path.isfile(p):
                return None
            fp = p
        if not fp:
            return None
        mn = 'py_mod_' + hashlib.md5(fp.encode()).hexdigest()
        if mn in sys.modules:
            del sys.modules[mn]
        spec = importlib.util.spec_from_file_location(mn, fp)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules[mn] = mod
        return mod
    except Exception:
        return None


class BaseSpider:
    """OK影视 py 蜘蛛契约基类（默认实现）"""

    def getName(self):
        return "AjeoZB-DB"

    def getDependence(self):
        # OK影视 引擎 init 阶段无条件调用（app.py getDependence），缺失会 AttributeError 导致站点加载失败
        return []

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return False

    def init(self, extend=""):
        pass

    def homeContent(self, filter=False):
        return {"class": [], "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg="1", filter=True, extend=""):
        return {"list": [], "page": 1, "pagecount": 1}

    def detailContent(self, ids, flags=None):
        return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        return {"parse": 0, "playUrl": "", "url": id}

    def localProxy(self, params):
        return []

    def action(self, action):
        return {}

    def destroy(self):
        return None


# ============================ 主蜘蛛 ============================
class Spider(BaseSpider):
    def __init__(self):
        super().__init__()
        self._sources = []          # 规范化后的源配置列表
        self._source_by_name = {}   # name -> cfg
        self._classes = []          # 分类列表
        self._categories = {}       # name -> 频道列表缓存（vod 列表）
        self._py_spiders = {}       # name -> py 子爬虫实例
        self._py_modules = {}       # name -> py 子模块
        self._py_vod_sources = {}   # name -> 点播型子源（无 liveContent，需透传）
        self._host_cache = {}       # host -> 'alive'/'dead'
        self._lock = threading.RLock()
        # 子源加载状态：主分类本地立即就绪，子源联网放后台线程，避免实例化卡死
        self._py_loaded = False
        self._py_loading = False
        self._py_ready = threading.Event()
        if requests is not None:
            self._session = requests.Session()
            self._session.headers.update({'User-Agent': DEFAULT_UA})
            self._session.verify = False
        else:
            self._session = None
        # 实例化即构建主源分类（纯本地、秒回）；子源联网加载异步进行
        self._build_main_sources({})
        self._start_py_preload()

    # ---------------- 初始化 ----------------
    def _normalize_config(self, cfg):
        c = dict(cfg)
        ua = c.pop('ua', None) or c.pop('user-agent', None) or c.pop('User-Agent', None)
        header = c.pop('header', None)
        headers = c.pop('headers', None)
        hdrs = {}
        if isinstance(headers, dict):
            hdrs.update(headers)
        elif isinstance(headers, str):
            try:
                hdrs.update(json.loads(headers))
            except Exception:
                pass
        if isinstance(header, dict):
            hdrs.update(header)
        if ua:
            hdrs['User-Agent'] = ua
        c['headers'] = hdrs
        c.setdefault('live_filter', False)
        c.setdefault('play_parse', False)
        return c

    def _build_main_sources(self, ext):
        """只构建主源列表与分类（纯本地，不联网，毫秒级返回）"""
        ext = ext if isinstance(ext, dict) else {}
        raw = ext.get('lives') if ext.get('lives') else LIVS_SOURCES
        if not isinstance(raw, list):
            raw = LIVS_SOURCES
        py_base = ''
        if ext.get('py_base'):
            py_base = str(ext['py_base']).rstrip('/') + '/'
        with self._lock:
            self._sources = []
            self._classes = []
            self._source_by_name = {}
            for item in raw:
                if not isinstance(item, dict):
                    continue
                cfg = self._normalize_config(item)
                name = cfg.get('name', '').strip()
                if not name:
                    continue
                if cfg.get('api') and py_base and not str(cfg['api']).startswith(('http://', 'https://', 'ftp://')):
                    cfg['api'] = py_base + str(cfg['api']).lstrip('./.\\')
                cfg['name'] = name
                self._sources.append(cfg)
                self._source_by_name[name] = cfg
                self._classes.append({'type_id': name, 'type_name': name})

    def _start_py_preload(self):
        """启动后台线程加载 py 子源（不阻塞实例化与首页）"""
        with self._lock:
            if self._py_loaded or self._py_loading:
                return
            self._py_loading = True
        try:
            t = threading.Thread(target=self._preload_py_sources, daemon=True)
            t.start()
        except Exception:
            with self._lock:
                self._py_loading = False
                self._py_ready.set()

    def _preload_py_sources(self):
        """后台线程：下载/加载 py 子源、实例化、合并点播子源分类（失败不阻塞）"""
        try:
            self._load_py_sources()
        except Exception:
            pass
        finally:
            with self._lock:
                self._py_loading = False
                self._py_loaded = True
            self._py_ready.set()

    def _load_py_sources(self):
        """联网加载 py 子源模块 + 实例化 + 合并点播子源分类（可后台线程或惰性调用）"""
        with self._lock:
            sources = list(self._sources)
        for cfg in sources:
            if not cfg.get('api'):
                continue
            try:
                mod = load_py_module(cfg['api'])
                if mod is None or not hasattr(mod, 'Spider'):
                    continue
                spider = mod.Spider()
                spider.init('{}')
                with self._lock:
                    self._py_modules[cfg['name']] = mod
                    self._py_spiders[cfg['name']] = spider
                    if not hasattr(spider, 'liveContent'):
                        self._py_vod_sources[cfg['name']] = True
            except Exception:
                continue
        # 点播型子源：合并其分类（带前缀避免与聚合器分类冲突）
        # 注意：绝不可调子源 homeContent() 合并——点播子源 homeContent 常联网握手
        # （如咕噜央视 53s），会拖死后台线程；分类是静态的，直接读 _categories
        with self._lock:
            vod_names = list(self._py_vod_sources.keys())
        for name in vod_names:
            try:
                sub = self._py_spiders[name]
                sub_classes = self._sub_static_classes(sub)
                for c in sub_classes:
                    if not (c and c.get('type_id')):
                        continue
                    with self._lock:
                        exists = any(x.get('type_id') == name + '::' + str(c['type_id']) for x in self._classes)
                        if not exists:
                            self._classes.append({
                                'type_id': name + '::' + str(c['type_id']),
                                'type_name': str(c.get('type_name') or c['type_id']),
                            })
            except Exception:
                continue

    @staticmethod
    def _sub_static_classes(sub):
        """从子源静态分类属性取分类，绝不联网。
        支持 _categories=[("id","名")] 与 _categories=[{"type_id","type_name"}] 两种形态；
        读不到时返回 []（分类合并静默跳过，不阻塞）。"""
        try:
            cats = getattr(sub, '_categories', None)
            if not cats:
                return []
            out = []
            for c in cats:
                if isinstance(c, dict):
                    if c.get('type_id'):
                        out.append({'type_id': str(c['type_id']), 'type_name': str(c.get('type_name') or c['type_id'])})
                elif isinstance(c, (tuple, list)) and len(c) >= 2:
                    out.append({'type_id': str(c[0]), 'type_name': str(c[1] or c[0])})
            return out
        except Exception:
            return []

    def _ensure_py_loaded(self, timeout=0.0):
        """确保子源已加载：已加载→直接返回；后台加载中→最多等 timeout 秒；未启动→同步执行。
        homeContent 用 timeout=0（秒回），categoryContent 等业务入口用较小 timeout。"""
        if self._py_loaded:
            return
        if self._py_loading:
            self._py_ready.wait(timeout)
            return
        with self._lock:
            if self._py_loaded:
                return
            self._py_loading = True
        try:
            self._load_py_sources()
        except Exception:
            pass
        finally:
            with self._lock:
                self._py_loading = False
                self._py_loaded = True
            self._py_ready.set()

    def init(self, extend=""):
        """init(extend)：extend 为 OK影视 传入的 JSON 字符串，可为空"""
        try:
            ext = json.loads(extend) if extend else {}
        except Exception:
            ext = {}
        self._build_main_sources(ext)
        self._start_py_preload()
        return ''

    # ---------------- 首页 ----------------
    def homeContent(self, filter=False):
        # 秒回：主分类已就绪；子源分类若后台已完成则一并包含
        with self._lock:
            classes = list(self._classes)
        return {"class": classes, "filters": {}, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def homeVod(self):
        return {"list": []}

    # ---------------- 分类频道 ----------------
    def categoryContent(self, tid, pg="1", filter=True, extend=""):
        try:
            page = max(1, int(pg)) if str(pg).isdigit() else 1
        except Exception:
            page = 1
        # 业务入口：确保子源已加载（后台线程若还在跑则最多等 8 秒；主源分类不受影响）
        self._ensure_py_loaded(timeout=8.0)
        # 点播型子源透传：tid = 源名::子分类id
        if '::' in str(tid):
            src_name, sub_tid = str(tid).split('::', 1)
            sub = self._py_spiders.get(src_name)
            if sub is not None and hasattr(sub, 'categoryContent'):
                try:
                    result = sub.categoryContent(sub_tid, page, filter, extend)
                    if isinstance(result, dict) and result.get('list'):
                        # 给每个 vod_id 加源名前缀，使 detailContent 能路由回子源
                        for v in result.get('list'):
                            if isinstance(v, dict) and v.get('vod_id'):
                                v['vod_id'] = src_name + '::' + str(v['vod_id'])
                        return result
                except Exception:
                    pass
                return {"list": [], "page": page, "pagecount": 1}
        # 兼容父级分类：tid 直接等于点播型 py 子源名（无 ::）时，透传该子源第一个分类，
        # 否则 OK影视 首页点击"📡咕噜央视"父标签会落到 _source_by_name 查无 → 找不到数据。
        # 注意仅点播型（_py_vod_sources）走此分支；m3u 型子源（央卫直播）走下方 _get_category_vods
        if str(tid) in self._py_vod_sources:
            sub = self._py_spiders.get(str(tid))
            if sub is not None and hasattr(sub, 'categoryContent'):
                sub_tid = ''
                try:
                    sub_classes = self._sub_static_classes(sub)
                    if sub_classes:
                        sub_tid = str(sub_classes[0]['type_id'])
                except Exception:
                    sub_tid = ''
                if sub_tid:
                    try:
                        result = sub.categoryContent(sub_tid, page, filter, extend)
                        if isinstance(result, dict) and result.get('list'):
                            for v in result.get('list'):
                                if isinstance(v, dict) and v.get('vod_id'):
                                    v['vod_id'] = str(tid) + '::' + str(v['vod_id'])
                            return result
                    except Exception:
                        pass
            return {"list": [], "page": page, "pagecount": 1}
        cfg = self._source_by_name.get(tid)
        if not cfg:
            return {"list": [], "page": page, "pagecount": 1}
        vods = self._get_category_vods(tid, cfg)
        total = len(vods)
        page_size = 30
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "list": vods[start:end],
            "page": page,
            "pagecount": max(1, (total + page_size - 1) // page_size),
            "limit": page_size,
            "total": total,
        }

    def _get_category_vods(self, tid, cfg):
        with self._lock:
            if tid in self._categories:
                return self._categories[tid]
        try:
            if cfg.get('api'):
                channels = self._load_py_channels(cfg)
            else:
                channels = self._load_url_channels(cfg)
        except Exception:
            channels = []
        vods = self._build_vods(cfg['name'], channels, cfg)
        with self._lock:
            self._categories[tid] = vods
        return vods

    # ---------------- py 子源加载 ----------------
    def _load_py_channels(self, cfg):
        """加载 py 子爬虫的 liveContent()，解析 m3u 得到频道列表"""
        name = cfg['name']
        spider = self._py_spiders.get(name)
        if spider is None:
            mod = load_py_module(cfg['api'])
            if mod is None or not hasattr(mod, 'Spider'):
                return []
            try:
                spider = mod.Spider()
                spider.init('{}')
                self._py_spiders[name] = spider
            except Exception:
                return []
        try:
            content = spider.liveContent('')
        except Exception:
            return []
        if not content:
            return []
        if isinstance(content, (list, tuple)) and len(content) >= 3:
            # 个别子爬虫 liveContent 返回 [code, type, body]
            content = content[2] if isinstance(content[2], str) else ''
        channels = self._parse_m3u(content, name)
        # 给子爬虫生成的 proxy URL 附加 __src，让本聚合器 localProxy 精确路由
        for ch in channels:
            u = ch.get('url', '')
            if u and '://' in u and 'fun=' in u and '__src=' not in u:
                sep = '&' if '?' in u else '?'
                ch['url'] = u + sep + '__src=' + name
        return channels

    # ---------------- url 源加载 ----------------
    def _load_url_channels(self, cfg):
        name = cfg['name']
        url = cfg.get('url', '')
        if not url:
            return []
        if not url.startswith(('http://', 'https://', 'ftp://')):
            p = resolve_py_path(url)
            if p and os.path.isfile(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return self._parse_content(content, name, cfg)
                except Exception:
                    return []
            return []
        try:
            headers = dict(cfg.get('headers', {}))
            if 'User-Agent' not in headers:
                headers['User-Agent'] = DEFAULT_UA
            content = http_get_text(url, headers=headers, timeout=REQ_TIMEOUT)
            if not content:
                return []
            content = try_decrypt_content(content, url)
            return self._parse_content(content, name, cfg)
        except Exception:
            return []

    # ---------------- 内容解析（移植 JS parseContent/parseM3u/parseFm/parseList）----------------
    def _parse_content(self, content, source_name, cfg=None):
        if not content:
            return []
        content = content.strip()
        if content.startswith('#EXTM3U') or content.startswith('#EXTINF'):
            return self._parse_m3u(content, source_name)
        if content.startswith('{') or content.startswith('['):
            try:
                data = json.loads(content)
                return self._parse_json(data, source_name)
            except Exception:
                pass
        if '#genre#' in content:
            return self._parse_txt(content, source_name, cfg)
        # 兜底：按普通 txt（分组,频道）解析
        return self._parse_txt(content, source_name, cfg)

    def _parse_m3u(self, content, source_name):
        channels = []
        current = None
        group = source_name
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('#EXTINF'):
                current = {'name': '', 'group': group}
                m = re.search(r'tvg-name="([^"]*)"', line)
                if m:
                    current['name'] = m.group(1)
                m = re.search(r'group-title="([^"]*)"', line)
                if m:
                    current['group'] = m.group(1)
                m = re.search(r'tvg-logo="([^"]*)"', line)
                if m:
                    current['logo'] = m.group(1)
                m = re.search(r',([^,]+)\s*$', line)
                if m and not current['name']:
                    current['name'] = m.group(1).strip()
            elif line and not line.startswith('#') and current is not None:
                current['url'] = line
                if current.get('name') and current.get('url'):
                    channels.append(current)
                current = None
        return channels

    def _parse_txt(self, content, source_name, cfg=None):
        channels = []
        group = source_name
        live_filter = bool(cfg and cfg.get('live_filter'))
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if '#genre#' in line:
                group = line.split(',')[0].strip()
                continue
            if ',' in line:
                parts = line.split(',', 1)
                name = parts[0].strip()
                url = parts[1].strip()
                if name and url:
                    if live_filter and not self._check_host_alive(url):
                        continue
                    channels.append({'name': name, 'group': group, 'url': url})
        return channels

    def _parse_json(self, data, source_name):
        channels = []

        def _extract(item, group=None):
            if not isinstance(item, dict):
                return None
            name = item.get('name') or item.get('title') or item.get('channel') or item.get('prov')
            url = item.get('url') or item.get('link') or item.get('playUrl')
            if name and url:
                return {'name': str(name).strip(), 'group': group or source_name, 'url': str(url).strip()}
            return None

        if isinstance(data, list):
            for item in data:
                ch = _extract(item)
                if ch:
                    channels.append(ch)
        elif isinstance(data, dict):
            # 兼容 {"channel":[...], "urls":[...]}（FM 格式）与 {"datalist":..., "urls":...}
            ch_list = data.get('channel') or data.get('channels') or data.get('datalist')
            if isinstance(ch_list, list):
                for item in ch_list:
                    if isinstance(item, dict):
                        name = item.get('name') or item.get('prov')
                        urls = item.get('urls') or item.get('datalist')
                        if isinstance(urls, list):
                            for u in urls:
                                if isinstance(u, str):
                                    channels.append({'name': str(name).strip(), 'group': source_name, 'url': u.strip()})
                                elif isinstance(u, dict):
                                    un = u.get('name')
                                    for k in ('url', 'link', 'playUrl', 'vod_play_url'):
                                        uv = u.get(k)
                                        if uv and isinstance(uv, str):
                                            channels.append({
                                                'name': str(un or name).strip(),
                                                'group': source_name,
                                                'url': uv.strip(),
                                            })
                                            break
            for k, v in data.items():
                if isinstance(v, list):
                    for item in v:
                        ch = _extract(item, group=k)
                        if ch:
                            channels.append(ch)
                elif isinstance(v, dict):
                    ch = _extract(v, group=k)
                    if ch:
                        channels.append(ch)
        return channels

    # ---------------- 频道 → vod（移植 saveCategoryItem）----------------
    def _build_vods(self, source_name, channels, cfg):
        """把频道按分组打包成 vod：一个分组=一个 vod（直播转点播粒度），
           vod_play_url = 频道名$url#频道名$url
        """
        groups = {}
        for ch in channels:
            g = ch.get('group') or '默认分类'
            groups.setdefault(g, []).append(ch)
        vods = []
        for gname, chs in groups.items():
            play_urls = []
            for ch in chs:
                play_urls.append(ch['name'] + '$' + ch['url'])
            vods.append({
                'vod_id': source_name + '$$$' + gname,
                'vod_name': gname,
                'vod_pic': PIC_URL,
                'vod_remarks': '',
                'type_name': '',
                'vod_year': '',
                'vod_area': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_content': '',
                'vod_play_from': source_name,
                'vod_play_url': '#'.join(play_urls),
            })
        return vods

    # ---------------- 详情 ----------------
    def detailContent(self, ids, flags=None):
        self._ensure_py_loaded(timeout=8.0)
        try:
            vid = ids[0] if isinstance(ids, list) else str(ids)
        except Exception:
            vid = str(ids)
        # 点播子源透传
        if '::' in str(vid):
            src_name, sub_vid = str(vid).split('::', 1)
            sub = self._py_spiders.get(src_name)
            if sub is not None and hasattr(sub, 'detailContent'):
                try:
                    result = sub.detailContent([sub_vid])
                    if isinstance(result, dict) and result.get('list'):
                        return self._tag_sub_playurl(src_name, result)
                except Exception:
                    pass
        parts = vid.split('$$$')
        if len(parts) < 2:
            return {"list": []}
        source_name = parts[0]
        group_name = parts[1]
        cfg = self._source_by_name.get(source_name)
        if not cfg:
            return {"list": []}
        vods = self._get_category_vods(source_name, cfg)
        for v in vods:
            if v['vod_name'] == group_name:
                return {"list": [v]}
        return {"list": []}

    # ---------------- 播放（含咪咕 302 签名）----------------
    def playerContent(self, flag, id, vipFlags=None):
        self._ensure_py_loaded(timeout=8.0)
        play_url = id or ''
        headers = {}
        # 点播子源播放地址透传：带 源名:: 前缀时交给子源 playerContent 解析
        if '::' in play_url:
            src_name, sub_url = play_url.split('::', 1)
            sub = self._py_spiders.get(src_name)
            if sub is not None and hasattr(sub, 'playerContent'):
                try:
                    result = sub.playerContent(flag, sub_url, vipFlags)
                    if isinstance(result, dict) and result.get('url'):
                        return result
                except Exception:
                    pass
            play_url = sub_url
        # 咪咕 302 签名中转：每次点播实时请求入口拿带签名的最终 m3u8 直链
        if MIGU_HOST in play_url:
            resolved = self._resolve_signed_url(play_url)
            if resolved and '://' in resolved:
                play_url = resolved
        return {"parse": 0, "playUrl": "", "url": play_url, "header": headers}

    def _tag_sub_playurl(self, src_name, result):
        """给点播子源 detailContent 返回的每个播放地址加 源名:: 前缀，
           使 playerContent 能路由回对应子源解析真实直链
        """
        try:
            for vod in result.get('list') or []:
                if not isinstance(vod, dict):
                    continue
                play_from = vod.get('vod_play_from') or ''
                play_url = vod.get('vod_play_url') or ''
                if not play_url:
                    continue
                if isinstance(play_url, str):
                    # 每个 $ 后的地址段加前缀（保留 $ 前的名称），已带前缀的跳过
                    first_addr = play_url.split('#')[0].split('$', 1)[1] if '$' in play_url else play_url
                    if src_name + '::' in first_addr:
                        continue
                    tagged = []
                    for ep in play_url.split('#'):
                        if '$' in ep:
                            nm, addr = ep.split('$', 1)
                            tagged.append(nm + '$' + src_name + '::' + addr)
                        else:
                            tagged.append(src_name + '::' + ep)
                    vod['vod_play_url'] = '#'.join(tagged)
        except Exception:
            pass
        return result

    def _sub_play_url(self, src_name, sub_url):
        """点播子源播放地址透传：子源若自带 playerContent 且可处理该地址则调用"""
        sub = self._py_spiders.get(src_name)
        if sub is not None and hasattr(sub, 'playerContent'):
            try:
                result = sub.playerContent('', sub_url, '')
                if isinstance(result, dict):
                    u = result.get('url') or ''
                    if u:
                        return u
            except Exception:
                pass
        return sub_url

    def _resolve_signed_url(self, url):
        try:
            resp = self._session.get(url, timeout=REQ_TIMEOUT, allow_redirects=True,
                                     headers={'User-Agent': DEFAULT_UA}) if self._session else None
            if resp is None:
                return url
            if resp.url and '://' in resp.url and resp.url != url:
                return resp.url
            loc = resp.headers.get('location') or resp.headers.get('Location')
            if loc and '://' in loc:
                return loc
        except Exception:
            pass
        return url

    # ---------------- localProxy（转发 py 子源）----------------
    def localProxy(self, params):
        """OK影视 播放 py 子源频道时回调：把 fun=cctv&id=xxx 等参数
           转发给对应子爬虫的 localProxy()
        """
        if not params or not isinstance(params, dict):
            return []
        self._ensure_py_loaded(timeout=8.0)
        src = params.get('__src')
        candidates = []
        if src and src in self._py_spiders:
            candidates = [src]
        else:
            candidates = list(self._py_spiders.keys())
        for name in candidates:
            spider = self._py_spiders.get(name)
            if spider is None:
                continue
            try:
                clean = {k: v for k, v in params.items() if k != '__src'}
                # 点播型子源 localProxy 用 url 参数；m3u 型用 fun/id 等
                if self._py_vod_sources.get(name) and not clean.get('url'):
                    clean['url'] = clean.get('u') or ''
                result = spider.localProxy(clean)
                if (isinstance(result, (list, tuple)) and len(result) >= 2 and
                        isinstance(result[0], int) and 200 <= result[0] < 300):
                    return list(result)
            except Exception:
                continue
        return []

    # ---------------- 搜索（移植 JS search 去重逻辑）----------------
    def searchContent(self, key, quick=False, pg="1"):
        self._ensure_py_loaded(timeout=8.0)
        kw = (key or '').strip()
        if not kw:
            return {"list": []}
        kw_lower = kw.lower()
        kw_compact = re.sub(r'\s+', '', kw_lower)

        def match_continuous(text):
            if not text:
                return False
            t = str(text).lower()
            if kw_lower in t:
                return True
            if kw_compact in re.sub(r'\s+', '', t):
                return True
            return False

        # 冷启动：确保所有分类已加载
        for cfg in self._sources:
            try:
                self._get_category_vods(cfg['name'], cfg)
            except Exception:
                continue

        results = []
        seen = set()

        # 点播型子源：转发其 searchContent 并合并
        for name in self._py_vod_sources:
            sub = self._py_spiders.get(name)
            if sub is None or not hasattr(sub, 'searchContent'):
                continue
            try:
                sub_result = sub.searchContent(kw, quick)
                for v in (sub_result.get('list') or []):
                    if not isinstance(v, dict):
                        continue
                    vname = v.get('vod_name') or ''
                    dk = vname + '\x1f' + (v.get('vod_id') or '')
                    if dk in seen:
                        continue
                    seen.add(dk)
                    v['vod_id'] = name + '::' + str(v.get('vod_id') or '')
                    results.append(v)
            except Exception:
                continue

        for source_name, vods in self._categories.items():
            for vod in vods:
                group_name = vod.get('vod_name') or ''
                play_url = vod.get('vod_play_url') or ''
                episodes = play_url.split('#')
                hit = []
                for ep in episodes:
                    seg = ep.split('$')
                    if len(seg) >= 2 and match_continuous(seg[0]):
                        hit.append(ep)
                if hit:
                    for ep in hit:
                        ep_parts = ep.split('$')
                        ep_name = ep_parts[0]
                        ep_url = '$'.join(ep_parts[1:])
                        dk = (ep_name or '') + '\x1f' + (ep_url or '')
                        if dk in seen:
                            continue
                        seen.add(dk)
                        results.append({
                            'vod_id': source_name + '$$$' + group_name + '$$$' + str(episodes.index(ep)),
                            'vod_name': ep_name,
                            'vod_pic': PIC_URL,
                            'vod_remarks': '直播',
                            'vod_play_from': source_name,
                            'vod_play_url': ep,
                        })
                elif match_continuous(group_name):
                    dk = (group_name or '') + '\x1f' + (play_url or '')
                    if dk in seen:
                        continue
                    seen.add(dk)
                    results.append({
                        'vod_id': source_name + '$$$' + group_name,
                        'vod_name': group_name,
                        'vod_pic': PIC_URL,
                        'vod_remarks': '直播',
                        'vod_play_from': source_name,
                        'vod_play_url': play_url,
                    })
        return {"list": results}

    # ---------------- live_filter host 探测 ----------------
    def _check_host_alive(self, url):
        try:
            host = urlparse(url).netloc
        except Exception:
            m = re.search(r'://([^/]+)', url or '')
            host = m.group(1) if m else None
        if not host:
            return True
        if host in self._host_cache:
            return self._host_cache[host] == 'alive'
        alive = False
        try:
            # 探测 host 是否可访问（Range 请求 1 字节即可）。requests 与 urllib 双通道，
            # 确保 OK影视 Chaquopy 环境（可能无 requests）也能探测
            if requests is not None and self._session is not None:
                resp = self._session.get(url, timeout=LIVE_FILTER_TIMEOUT,
                                         headers={'Range': 'bytes=0-1', 'User-Agent': 'okhttp/3.12.13'})
                if resp is not None and 200 <= resp.status_code < 400:
                    alive = True
            else:
                req = urllib.request.Request(url, headers={'Range': 'bytes=0-1', 'User-Agent': 'okhttp/3.12.13'})
                with urllib.request.urlopen(req, timeout=LIVE_FILTER_TIMEOUT) as r:
                    if 200 <= r.status < 400:
                        alive = True
        except Exception:
            alive = False
        self._host_cache[host] = 'alive' if alive else 'dead'
        return alive


# ============ 模块级双入口（drpy site 模式 / 旧内核兼容） ============
# 与咕噜咕噜直播.py 成功模式一致：OK影视 站点型 py 引擎可能直接调用
# 模块级函数（或实例化后调用类方法），两者都要提供。

_SINGLETON = None


def _get_singleton():
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Spider()
    return _SINGLETON


def init(extend=""):
    return _get_singleton().init(extend)


def homeContent(filter=False):
    return _get_singleton().homeContent(filter)


def homeVideoContent():
    return _get_singleton().homeVideoContent()


def categoryContent(tid, pg="1", filter=True, extend=""):
    return _get_singleton().categoryContent(tid, pg, filter, extend)


def detailContent(ids, flags=None):
    return _get_singleton().detailContent(ids)


def searchContent(key, quick=False, pg="1"):
    return _get_singleton().searchContent(key, quick)


def playerContent(flag, ids, vipFlags=None):
    return _get_singleton().playerContent(flag, ids, vipFlags)


def localProxy(params):
    return _get_singleton().localProxy(params)


def getName():
    return _get_singleton().getName()


# 类名别名（部分内核按小写 spider 约定取类）
spider = Spider
