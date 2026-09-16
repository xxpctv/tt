# -*- coding: utf-8 -*-
"""
喵喵短剧 Qmdj 独立版
协议：qmplaylet 短剧体系（neptune.qmplaylet.com 域名表 -> api-store/api-read）
  - 首页/分类: GET api-store.qmplaylet.com/api/v1/playlet/index
  - 详情:      GET api-read.qmplaylet.com/player/api/v1/playlet/info?playlet_id=
  - 搜索:      GET api-store.qmplaylet.com/api/v1/playlet/search
  - 播放:      info 返回 m3u8 直链（cdn-vod-playlet.wtzw.com），无防盗链
签名（已 100% 破解，5+6 抓包样本全命中）：
  - query sign  = MD5( TreeMap 字典序 k=v 无分隔连拼 + 盐 )
  - header sign = MD5( 'AUTHORIZATION=app-version=10001application-id=com.duoduo.read'
                       'channel=va-vivo_lfis-white=net-env=1platform=android'
                       'qm-params=' + <qm_params> + 'reg=' + 盐 )
  - 盐 = d3dGiJc651gSQ8w1（Qmdj.smali :array_1a，16bit 变体 key=0x70BD 解出）
qm-params（逆向进度）：
  - 生成链：LinkedHashMap{解密键:currentTimeMillis} -> Gson.toJson -> Base64.NO_WRAP -> 字符替换
  - 替换：'+'->'P' '/'->'X' 数字->:array_4c8 大写->:array_4d6 小写->:array_4f4
  - 小写表已解 = mBOuc6Kx5T-2zSZ1VvjQ7DwnLe；大写/数字表未解
  - 当前使用抓包完整样本（服务端时间戳宽容已验证：数小时前样本重放 200）
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import re
import time
import hashlib
import urllib.parse
import urllib.request
import gzip

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_DBG = True


def _dbg(msg):
    if not _DBG:
        return
    try:
        with open('/sdcard/Download/qmdj_dbg.log', 'a') as _f:
            _f.write(msg + chr(10))
    except Exception:
        pass


_UA = ('Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011) '
       'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/107.0.0.0 Safari/537.36')

_SALT = 'd3dGiJc651gSQ8w1'

# 抓包完整 qm-params（576 字符，时间戳宽容）
_QM_PARAMS = 'cLGeuyoMmqN6OlNDOzf5A5HwtTK5taGUuq2-HTZ5gI9wgI9wgI9QNz4E4LU2geFEth9wgI9QgI9wgI9wgI9wgI9wH5w5pyRlmqN2tq2-HTZ5gT9LNh9MgI0LgT0egTglpz0LpqFUgepxpqFUAIk2gyNTAy0l4h9YpzfLpTG-NI9nNzN-4eR54eOMpTG-Nq45taGQ4qg5A5H5taGeBERL4lRUmqF5A5HYNI-MAI0E4h9L4h-eNIgUH5w5OzRzOzRemaUMcCs2HTZ5gaHjHzUDpyRjHTZ5hhHwghGtghsIH5w5uln5tq2Qpq-5A5H5taGTBy22BSFQmqF5A5Hl4zNTNI4Ygh2-ghs-gIpxH5w54SGxBzF5A5G3pqkQm3HjHzJxmqF5A5H5taGD4q2-tqYDtqNx4lx2HTZ5H5w5OE2etCp2O5HWHT0nH5w5u_GUOEk2paU1paHWH5HjHSsZBlY2tqn2uzRjHTZ53aHjHz2Qpq-5A5H5taGEByHQuq2-HTZ5NzGT4eFlAh0YpI0wpI9l43HjHSN2OEN1BlrQmqF5A5HnNeKYNhfegI4rgIOnHSM='

_INDEX = 'https://api-store.qmplaylet.com/api/v1/playlet/index'
_INFO = 'https://api-read.qmplaylet.com/player/api/v1/playlet/info'
_SEARCH = 'https://api-store.qmplaylet.com/api/v1/playlet/search'

_TRACK_PREFIX = '6bcc46919d10d06a'

_HEADER_TPL = ('AUTHORIZATION=app-version=10001application-id=com.duoduo.read'
               'channel=va-vivo_lfis-white=net-env=1platform=android'
               'qm-params=%sreg=')


def _query_sign(params):
    seg = ''.join('%s=%s' % (k, params[k]) for k in sorted(params))
    return hashlib.md5((seg + _SALT).encode()).hexdigest()


def _header_sign():
    return hashlib.md5((_HEADER_TPL % _QM_PARAMS + _SALT).encode()).hexdigest()


def _get(url, params):
    qs = dict(params)
    qs['sign'] = _query_sign(qs)
    full = url + '?' + urllib.parse.urlencode(qs)
    req = urllib.request.Request(full, headers={
        'User-Agent': _UA,
        'authorization': '',
        'no-permiss': '3',
        'net-env': '1',
        'reg': '',
        'channel': 'va-vivo_lf',
        'is-white': '',
        'platform': 'android',
        'application-id': 'com.duoduo.read',
        'user-agent': 'webviewversion/0',
        'app-version': '10001',
        'qm-params': _QM_PARAMS,
        'accept-encoding': 'gzip',
        'sign': _header_sign(),
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            if r.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
        try:
            obj = json.loads(raw.decode('utf-8', 'replace'))
            _dbg('GET %s -> code=%s len=%d' % (full[:200], obj.get('code'), len(raw)))
        except Exception:
            obj = {}
            _dbg('GET %s -> RAW len=%d head=%s' % (full[:200], len(raw), raw[:80]))
        return obj
    except Exception as e:
        _dbg('GET %s -> EXC %r' % (full[:200], e))
        return {}


def _clean_title(t):
    """去掉搜索返回标题里的 <font color=...> 高亮标签"""
    if not t:
        return t
    return re.sub(r'<[^>]+>', '', t)


def _vod_from_item(it):
    return {
        'vod_id': str(it.get('playlet_id', '')),
        'vod_name': it.get('title', ''),
        'vod_pic': it.get('image_link', ''),
        'vod_remarks': '%s集' % it.get('total_episode_num', '') if it.get('total_episode_num') else '',
        'vod_year': '',
        'vod_area': '',
        'vod_content': it.get('intro', ''),
    }


class Spider(_BaseSpider):
    name = '喵喵短剧'

    def init(self, extend=''):
        return ''

    # ================= 首页 =================
    def homeContent(self, filter):
        j = _get(_INDEX, {'playlet_privacy': '1', 'tag_id': '0', 'operation': '1'})
        d = j.get('data', {})
        classes = []
        seen = set()
        # 与原版一致：分类取 tag_items（完整 152 个 tag，含运营位）
        for t in (d.get('tag_items') or []):
            tid = str(t.get('tag_id'))
            name = t.get('tag_name', '')
            if tid in seen or not name:
                continue
            seen.add(tid)
            classes.append({'type_id': tid, 'type_name': name})
        lst = [_vod_from_item(it) for it in (d.get('list') or [])]
        return {'class': classes, 'list': lst}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        params = {'playlet_privacy': '1', 'tag_id': str(tid), 'operation': '1'}
        if pg > 1:
            params['next_id'] = str(pg - 1)
        j = _get(_INDEX, params)
        lst = [_vod_from_item(it) for it in (j.get('data', {}).get('list') or [])]
        return {'page': pg, 'pagecount': 9999, 'limit': 90, 'total': 9999, 'list': lst}

    # ================= 详情 =================
    def detailContent(self, ids):
        # 兼容两种壳传参：OK影视 传 List / 影视仓 传 String
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0])
        else:
            vid = str(ids)
        vid = vid.strip().strip("[]'\" ").strip()
        j = _get(_INFO, {'playlet_id': vid})
        d = j.get('data', {}) or {}
        eps = []
        for i, pl in enumerate(d.get('play_list') or [], 1):
            eps.append('第%s集$%s' % (i, pl.get('video_url', '')))
        vod = {
            'vod_id': vid,
            'vod_name': d.get('title') or vid,
            'vod_pic': d.get('image_link') or '',
            'type_name': d.get('tags') or '',
            'vod_remarks': ('%s集' % d.get('total_episode_num')) if d.get('total_episode_num') else '',
            'vod_content': d.get('intro') or '',
            'vod_play_from': '喵喵短剧',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    # ================= 播放 =================
    def playerContent(self, ids, vip, flag):
        # 原版 Qmdj 把第二参数（vip）作为播放地址，OK影视/影视仓均如此
        url = str(vip or ids or '')
        if '$' in url:
            url = url.split('$', 1)[1]
        return {'parse': 0, 'playUrl': '', 'url': url}

    # ================= 搜索 =================
    # OK影视 quickSearch=1 时调用 quickSearch(key)；影视仓调用 searchContent(key, quick)
    def quickSearch(self, key):
        return self.searchContent(key, True)

    def searchContent(self, key, quick=True):
        _dbg('SEARCH key=%r type=%s' % (key, type(key).__name__))
        k = str(key or '').strip()
        # 兼容壳已 URL 编码的 key（双重编码会导致搜不到）
        if '%' in k:
            try:
                k2 = urllib.parse.unquote(k)
                if k2 != k:
                    _dbg('SEARCH unquote %r -> %r' % (k, k2))
                    k = k2
            except Exception:
                pass
        track = _TRACK_PREFIX + str(int(time.time() * 1000))
        j = _get(_SEARCH, {'extend': '', 'track_id': track, 'page': '1',
                           'wd': k, 'read_preference': '0'})
        lst = []
        for it in (j.get('data', {}).get('list') or []):
            lst.append({
                'vod_id': str(it.get('id', '')),
                'vod_name': _clean_title(it.get('title', '')),
                'vod_pic': it.get('image_link', ''),
                'vod_remarks': it.get('total_num', ''),
                'vod_content': it.get('sub_title', ''),
            })
        return {'list': lst}

    # ================= 本地自测 =================
    def localTest(self):
        out = []
        h = self.homeContent('')
        out.append('home: class=%d list=%d 首项=%s' % (
            len(h['class']), len(h['list']),
            (h['list'][0]['vod_name'] if h['list'] else '-')))
        c = self.categoryContent('1273', 1, '', '')
        out.append('cat1273: list=%d 首项=%s' % (len(c['list']), c['list'][0]['vod_name'] if c['list'] else '-'))
        d = self.detailContent('27665')
        vod = d['list'][0]
        out.append('detail: %s eps=%d from=%s' % (vod['vod_name'], len(vod['vod_play_url'].split('#')), vod['vod_play_from']))
        s = self.searchContent('月与灯依旧', True)
        out.append('search: %d 首项=%s' % (len(s['list']), s['list'][0]['vod_name'] if s['list'] else '-'))
        return '\n'.join(out)


if __name__ == '__main__':
    print(Spider().localTest())
