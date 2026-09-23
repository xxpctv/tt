# -*- coding: utf-8 -*-
"""
Ajeo-GuaziLive 瓜子体育（原 csp_GuaziLiveAmns -> GuaziTY）独立版
协议依据 aidaox/feimao jar 原版 com.github.catvod.spider.GuaziTY 全链路复现（已 100% 解明并实测解密 200）：
  - 端点：POST https://api.46d5umpk.com/gz/live/sports?parameter=key（列表）/ /gz/live/detail?parameter=key（详情）
  - 请求体：parameter = Base64(AES-CBC-PKCS5(明文参数JSON, key="KANGEQIU@8868!~.", iv="0200010900030207"))
  - 响应：json.data 字符串（去引号）-> Base64 解码 -> AES-CBC 解密 -> 明文 JSON
  - 头：User-Agent=okhttp/3.12.0, content-type=application/x-www-form-urlencoded,
        user-platform=null, client-version=3.0.1.1, client-channel="", token=""
  - 分类参数：hot={"frame":"0","hot":"1","tag":"0","type":"0"} / nba={"frame":"0","hot":"0","tag":"37","type":"0"}
             football={"frame":"0","hot":"0","tag":"0","type":"1"} / basketball={"frame":"0","hot":"0","tag":"0","type":"2"}
             未知 tid 用 hot 兜底（对齐原版）；pg != "1" 返回空（原版仅处理第一页）
  - 列表过滤：match_time*1000 >= now-1天 且 m_status < 2；m_status==1 的排前
  - 详情：live_line[] 每项 name$m3u8，playFrom="瓜子"
  - 播放：playerContent 直回 m3u8 + header{User-Agent: Lavf/57.83.100, Referer: http://WJiZxLXA2.com/}
兼容：OK影视 / 影视仓（TVBox Python 引擎）；AES 优先 pycryptodome，无依赖时回退内置纯 Python AES-128-CBC
"""
import base64
import json
import urllib.parse
import urllib.request
from datetime import datetime

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_KEY = b'KANGEQIU@8868!~.'
_IV = b'0200010900030207'

_PARAMS = {
    'hot': '{"frame":"0","hot":"1","tag":"0","type":"0"}',
    'nba': '{"frame":"0","hot":"0","tag":"37","type":"0"}',
    'football': '{"frame":"0","hot":"0","tag":"0","type":"1"}',
    'basketball': '{"frame":"0","hot":"0","tag":"0","type":"2"}',
}

_SPORTS = 'https://api.46d5umpk.com/gz/live/sports?parameter=key'
_DETAIL = 'https://api.46d5umpk.com/gz/live/detail?parameter=key'
_HEADERS = {
    'User-Agent': 'okhttp/3.12.0',
    'content-type': 'application/x-www-form-urlencoded',
    'user-platform': 'null',
    'client-version': '3.0.1.1',
    'client-channel': '',
    'token': '',
}

try:
    from Crypto.Cipher import AES as _PyCryptoAES
    from Crypto.Util.Padding import pad as _pc_pad, unpad as _pc_unpad
    _USE_PYCRYPTO = True
except Exception:
    _USE_PYCRYPTO = False

    def _xtime(a):
        r = []
        for b in a:
            c = b << 1
            if b & 0x80:
                c ^= 0x1B
            r.append(c & 0xFF)
        return r

    _SBOX = [
        0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
        0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
        0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
        0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
        0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
        0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
        0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
        0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
        0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
        0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
        0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
        0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
        0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
        0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
        0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
        0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16]

    def _aes_enc_block(s, k):
        def add(x, y):
            return [a ^ b for a, b in zip(x, y)]
        st = [[s[i + 4 * j] for i in range(4)] for j in range(4)]
        ks = []
        rk = list(k)
        rcon = 1
        for rnd in range(11):
            ks.append(rk[:])
            if rnd < 10:
                nrk = rk[:]
                t = nrk[13:16] + nrk[12:13]
                t = [_SBOX[x] for x in t]
                t[0] ^= rcon
                rcon = _xtime([rcon])[0]
                for i in range(4):
                    nrk[i] ^= t[i]
                for i in range(4, 16):
                    nrk[i] ^= nrk[i - 4]
                rk = nrk
        for rnd in range(11):
            kk = ks[rnd]
            for j in range(4):
                for i in range(4):
                    st[i][j] ^= kk[i + 4 * j]
            if rnd < 10:
                for j in range(4):
                    for i in range(4):
                        st[i][j] = _SBOX[st[i][j]]
                st = list(map(list, zip(*st)))
                for j in range(4):
                    t = st[j][:]
                    st[j][0] = t[0] ^ t[1] ^ t[2] ^ t[3]
                    st[j][1] = t[1] ^ t[2] ^ t[3] ^ t[0]
                    st[j][2] = t[2] ^ t[3] ^ t[0] ^ t[1]
                    st[j][3] = t[3] ^ t[0] ^ t[1] ^ t[2]
                for j in range(4):
                    for i in range(4):
                        st[i][j] = _xtime([st[i][j]])[0]
                for j in range(4):
                    t = st[j][:]
                    st[j][0] = t[0] ^ _xtime([t[1]])[0] ^ t[2] ^ t[3]
                    st[j][1] = t[1] ^ _xtime([t[2]])[0] ^ t[3] ^ t[0]
                    st[j][2] = t[2] ^ _xtime([t[3]])[0] ^ t[0] ^ t[1]
                    st[j][3] = t[3] ^ _xtime([t[0]])[0] ^ t[1] ^ t[2]
                st = list(map(list, zip(*st)))
                for j in range(4):
                    for i in range(4):
                        st[i][j] = _SBOX[st[i][j]]
        out = []
        for j in range(4):
            for i in range(4):
                out.append(st[i][j])
        return bytes(out)

    def _aes_cbc_encrypt(data, key, iv):
        out = b''
        prev = iv
        for i in range(0, len(data), 16):
            blk = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
            e = _aes_enc_block(list(blk), list(key))
            out += e
            prev = e
        return out

    def _aes_cbc_decrypt(data, key, iv):
        out = b''
        prev = iv
        for i in range(0, len(data), 16):
            blk = data[i:i + 16]
            e = _aes_enc_block(list(blk), list(key))
            out += bytes(a ^ b for a, b in zip(e, prev))
            prev = blk
        return out


def _pkcs5_pad(b):
    n = 16 - (len(b) % 16)
    return b + bytes([n]) * n


def _pkcs5_unpad(b):
    return b[:-b[-1]]


def _aes_encrypt(plain):
    data = plain.encode('utf-8')
    if _USE_PYCRYPTO:
        c = _PyCryptoAES.new(_KEY, _PyCryptoAES.MODE_CBC, _IV)
        return base64.b64encode(c.encrypt(_pc_pad(data, 16))).decode()
    return base64.b64encode(_aes_cbc_encrypt(_pkcs5_pad(data), _KEY, _IV)).decode()


def _aes_decrypt(b64):
    data = base64.b64decode(b64)
    if _USE_PYCRYPTO:
        c = _PyCryptoAES.new(_KEY, _PyCryptoAES.MODE_CBC, _IV)
        return _pc_unpad(c.decrypt(data), 16).decode('utf-8', 'replace')
    return _pkcs5_unpad(_aes_cbc_decrypt(data, _KEY, _IV)).decode('utf-8', 'replace')


def _api(url, plain):
    """原版 a(url, json明文)：AES 封装 POST + 解密响应 data"""
    body = urllib.parse.urlencode({'parameter': _aes_encrypt(plain)}).encode()
    req = urllib.request.Request(url, data=body, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            t = r.read().decode('utf-8', 'replace')
    except Exception:
        return None
    try:
        j = json.loads(t)
        data = j.get('data')
        if not isinstance(data, str) or not data:
            return None
        return _aes_decrypt(data.replace('"', ''))
    except Exception:
        return None


def _fmt_time(ts):
    try:
        return datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')
    except Exception:
        return ''


def _remarks(it):
    """event_name + 时间 + match_status_info（+ 比分）"""
    parts = [it.get('event_name') or '', _fmt_time(it.get('match_time') or 0), it.get('match_status_info') or '']
    s = ' '.join(p for p in parts if p)
    hs = it.get('home', {}).get('score')
    av = it.get('visiting', {}).get('score')
    try:
        hs_i, av_i = int(hs), int(av)
    except Exception:
        hs_i = av_i = 0
    if hs_i > 0 or av_i > 0:
        s = '%s 比分%d-%d' % (s, hs_i, av_i)
    return s


class Spider(_BaseSpider):
    name = '瓜子体育'
    siteKey = 'GuaziLive'

    def init(self, extend=''):
        return ''

    def homeContent(self, filter):
        classes = [
            {'type_id': 'hot', 'type_name': '热门'},
            {'type_id': 'nba', 'type_name': 'NBA'},
            {'type_id': 'football', 'type_name': '足球'},
            {'type_id': 'basketball', 'type_name': '篮球'},
        ]
        return {'class': classes, 'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        if str(pg or '') != '1':
            return {'list': []}
        if not tid:
            tid = 'hot'
        plain = _PARAMS.get(tid, _PARAMS['hot'])
        txt = _api(_SPORTS, plain)
        if not txt:
            return {'list': []}
        try:
            arr = json.loads(txt)
        except Exception:
            return {'list': []}
        if not isinstance(arr, list):
            return {'list': []}
        cutoff = (datetime.now().timestamp() - 86400) * 1000
        live, other = [], []
        for it in arr:
            if not isinstance(it, dict):
                continue
            try:
                mt = int(it.get('match_time') or 0) * 1000
            except Exception:
                mt = 0
            if mt < cutoff:
                continue
            try:
                ms = int(it.get('m_status') or 0)
            except Exception:
                ms = 0
            if ms >= 2:
                continue
            home = it.get('home') or {}
            visiting = it.get('visiting') or {}
            vod = {
                'vod_id': str(it.get('mid') or ''),
                'vod_name': '%s vs %s' % (home.get('name') or '', visiting.get('name') or ''),
                'vod_pic': home.get('logo') or '',
                'vod_remarks': _remarks(it),
            }
            if ms == 1:
                live.append(vod)
            else:
                other.append(vod)
        return {'list': live + other}

    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        txt = _api(_DETAIL, json.dumps({'mid': str(ids[0])}, ensure_ascii=False))
        if not txt:
            return {'list': []}
        try:
            obj = json.loads(txt)
        except Exception:
            return {'list': []}
        home = obj.get('home') or {}
        visiting = obj.get('visiting') or {}
        name = '%s vs %s' % (home.get('name') or '', visiting.get('name') or '')
        rem = obj.get('match_status_info') or ''
        try:
            hs_i, av_i = int(home.get('score') or 0), int(visiting.get('score') or 0)
        except Exception:
            hs_i = av_i = 0
        if hs_i > 0 or av_i > 0:
            rem = '%s 比分%d-%d' % (rem, hs_i, av_i)
        urls = []
        ll = obj.get('live_line')
        if isinstance(ll, list):
            for ln in ll:
                if not isinstance(ln, dict):
                    continue
                urls.append('%s$%s' % (ln.get('name') or '', ln.get('m3u8') or ''))
        if not urls:
            return {'list': []}
        vod = {
            'vod_id': str(ids[0]),
            'vod_name': name,
            'vod_pic': home.get('logo') or '',
            'vod_remarks': rem,
            'vod_content': rem,
            'vod_play_from': '瓜子',
            'vod_play_url': '#'.join(urls),
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {'url': '', 'msg': '播放地址为空'}
        return {
            'url': id,
            'header': {
                'User-Agent': 'Lavf/57.83.100',
                'Referer': 'http://WJiZxLXA2.com/',
            },
        }

    def searchContent(self, key, quick=True, pg=1):
        # 原版无搜索
        return {}


class GuaziLiveAmns(Spider):
    """OK影视 api=csp_GuaziLiveAmns 别名类"""
    pass


def main():
    s = Spider()
    h = s.homeContent(False)
    print('首页分类:', [c['type_name'] for c in h['class']])
    for tid in ('hot', 'nba'):
        c = s.categoryContent(tid, 1, None, None)
        print('[%s] 条数:' % tid, len(c['list']))
        if c['list']:
            print('  首项:', c['list'][0])
            d = s.detailContent([c['list'][0]['vod_id']])
            if d['list']:
                vod = d['list'][0]
                print('  详情:', vod['vod_name'], '|', vod['vod_remarks'], '| 线路:', vod['vod_play_from'])
                ep0 = vod['vod_play_url'].split('#')[0]
                pid = ep0.split('$')[1]
                p = s.playerContent('', pid, [])
                print('  播放:', p['url'][:90], '| header keys:', list(p['header'].keys()))


if __name__ == '__main__':
    main()
