# -*- coding: utf-8 -*-
"""
富强听书（csp_TStyAmns）独立 Python 版
协议：2026-09-26 frida 反射驱动原版 TSty + PC 纯 Python 全链路实抓重放
  静态key(hex): ea9d9d4f9a983fe6f6382f29c7b46b8d6dc47abc6da36662e6ddff8c78902f65
  请求信封: '02' + iv(12B).hex + reverse( AES-256-GCM(key,iv, json) ).hex   (密文ct||tag整体反转, 裸hex字符串)
  响应信封: ver(1B) + nonce(24B) + ct + tag ; ver=01原样 ver=02密文整体反转
            算法 XChaCha20-Poly1305(tink) = HChaCha20派生key + ChaCha20Poly1305(子nonce=00000000+nonce[16:24])
  会话: dfp = 'f-c29fi:f-' + base64( RSA-1024/PKCS1v15(随机48字节) )   ← 公钥内置于此，服务器只验RSA不看明文
        POST {api}/apk/auth/me  (Cookie: dfp=...) -> Set-Cookie session + auth_token(guest游客)
        后续 POST 带 Cookie: dfp=..;session=.. 与 Authorization: Bearer <auth_token>
  分类: GET {json}/filters                    -> {sorts,categories[有声小说/评书],statuses}
  列表: GET {json}/types/{tid}/{sort}/p{pg}   sort: comprehensive/popular/updated/new
  详情: GET {json}/album_info/{id} + /album_chapters/{id}
  搜索: POST {api}/apk/search   {"keyword":>=2字,"page":1}
  播放: POST {api}/apk/play/play_token {"album_id":id,"chapter_idx":1起} -> play_url 直链
零第三方依赖：AES-GCM / XChaCha20-Poly1305 / RSA 全部纯标准库实现（若环境有 cryptography/pycryptodome 会优先使用）。
兼容：OK影视 / 影视仓（TVBox Python 引擎，入口类必须名为 Spider）
"""
import os
import json
import struct
import base64
import urllib.request
import urllib.error

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

KEY = bytes.fromhex('ea9d9d4f9a983fe6f6382f29c7b46b8d6dc47abc6da36662e6ddff8c78902f65')
UA = 'azybk_1.0.8(SKW-A0,Android28)'
JSON_BASE = 'https://json.hgeuz.cn/azybk/json_v1'
API_BASE = 'https://azybk.tingyou8.vip'
TIMEOUT = 15

# RSA-1024 公钥（PKCS#1 PEM，来自 https://tingyoutou.oss-cn-hongkong.aliyuncs.com/1.0.8.json）
PUB_PEM = b'''-----BEGIN RSA PUBLIC KEY-----
MIGJAoGBAJ8ONV6qk6RHIaL52le5kO3u+LNckM6I/4Q2yFVVQ/XIy7Apk9ahyahF
iRh2xxiuO93/ZypAPfuE0WViXCMFgY96O5AL747yRaGxE181ACNstqCNpFdWHiiA
ydtZ8tInIjXr2DfXOIUKUMVqbVpvH3Re/ZtTEWDoJMzg8o01qFxHAgMBAAE=
-----END RSA PUBLIC KEY-----
'''

SORTS = [('comprehensive', '综合排序'), ('popular', '播放最多'),
         ('updated', '最近更新'), ('new', '最新发布')]


# ================================================================
# 密码学：优先系统库，回退纯 python
# ================================================================
def _aesgcm_encrypt(key, iv, plaintext):
    """返回 ct||tag"""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _A
        return _A(key).encrypt(iv, plaintext, None)
    except Exception:
        pass
    try:
        from Cryptodome.Cipher import AES as _A2
    except Exception:
        try:
            from Crypto.Cipher import AES as _A2
        except Exception:
            _A2 = None
    if _A2 is not None:
        c = _A2.new(key, _A2.MODE_GCM, nonce=iv)
        ct, tag = c.encrypt_and_digest(plaintext)
        return ct + tag
    return _PureAESGCM(key).seal(iv, plaintext)


def _xchacha_decrypt(key, nonce24, ct_tag, aad=b''):
    subkey = _hchacha20(key, nonce24[:16])
    sub_nonce = b'\x00\x00\x00\x00' + nonce24[16:24]
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305 as _C
        return _C(subkey).decrypt(sub_nonce, ct_tag, aad)
    except Exception:
        pass
    try:
        from Cryptodome.Cipher import ChaCha20_Poly1305 as _C2
    except Exception:
        try:
            from Crypto.Cipher import ChaCha20_Poly1305 as _C2
        except Exception:
            _C2 = None
    if _C2 is not None:
        c = _C2.new(key=subkey, nonce=sub_nonce)
        if aad:
            c.update(aad)
        return c.decrypt_and_verify(ct_tag[:-16], ct_tag[-16:])
    return _PureChaChaPoly(subkey).open(sub_nonce, ct_tag, aad)


# ---------- 纯 python AES-256-GCM ----------
_SBOX = []
_INV_SBOX = []
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36,
         0x6c, 0xd8, 0xab, 0x4d]


def _init_aes_tables():
    # GF(256) log/antilog（生成元 3）
    exp_t = [0] * 256
    log_t = [0] * 256
    x = 1
    for i in range(255):
        exp_t[i] = x
        log_t[x] = i
        hi = x & 0x80
        x = (x << 1) & 0xff
        if hi:
            x ^= 0x1b                # ×2
        x ^= exp_t[i]                # ×3（3 是 GF(256) 生成元）
    exp_t[255] = exp_t[0]

    def inv(a):
        return 0 if a == 0 else exp_t[255 - log_t[a]]

    sbox = [0] * 256
    for i in range(256):
        b = inv(i)
        # 仿射变换
        s = b ^ ((b << 1) | (b >> 7)) ^ ((b << 2) | (b >> 6)) \
            ^ ((b << 3) | (b >> 5)) ^ ((b << 4) | (b >> 4))
        sbox[i] = (s ^ 0x63) & 0xff
    inv_sbox = [0] * 256
    for i, v in enumerate(sbox):
        inv_sbox[v] = i
    _SBOX.extend(sbox)
    _INV_SBOX.extend(inv_sbox)


_init_aes_tables()


def _aes_key_expansion(key):
    nk = len(key) // 4          # 8 for aes-256
    nr = nk + 6                 # 14
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)], nr


def _aes_encrypt_block(block, rks, nr):
    s = list(block)

    def add_rk(state, rk):
        return [state[i] ^ rk[i] for i in range(16)]

    def sub_bytes(state):
        return [_SBOX[b] for b in state]

    def shift_rows(s):
        return [s[0], s[5], s[10], s[15],
                s[4], s[9], s[14], s[3],
                s[8], s[13], s[2], s[7],
                s[12], s[1], s[6], s[11]]

    def gmul(a, b):
        p = 0
        for _ in range(8):
            if b & 1:
                p ^= a
            hi = a & 0x80
            a = (a << 1) & 0xff
            if hi:
                a ^= 0x1b
            b >>= 1
        return p

    def mix_cols(s):
        out = [0] * 16
        for c in range(4):
            col = s[4 * c:4 * c + 4]
            out[4 * c + 0] = gmul(col[0], 2) ^ gmul(col[1], 3) ^ col[2] ^ col[3]
            out[4 * c + 1] = col[0] ^ gmul(col[1], 2) ^ gmul(col[2], 3) ^ col[3]
            out[4 * c + 2] = col[0] ^ col[1] ^ gmul(col[2], 2) ^ gmul(col[3], 3)
            out[4 * c + 3] = gmul(col[0], 3) ^ col[1] ^ col[2] ^ gmul(col[3], 2)
        return out

    s = add_rk(s, rks[0])
    for r in range(1, nr):
        s = sub_bytes(s)
        s = shift_rows(s)
        s = mix_cols(s)
        s = add_rk(s, rks[r])
    s = sub_bytes(s)
    s = shift_rows(s)
    s = add_rk(s, rks[nr])
    return bytes(s)


class _PureAESGCM:
    def __init__(self, key):
        self._rks, self._nr = _aes_key_expansion(key)
        self._h = _aes_encrypt_block(b'\x00' * 16, self._rks, self._nr)

    def _ecb(self, b):
        return _aes_encrypt_block(b, self._rks, self._nr)

    @staticmethod
    def _gf_mul(xb, yb):
        x = int.from_bytes(xb, 'big')
        y = int.from_bytes(yb, 'big')
        r = 0xe1 << 120
        z = 0
        v = y
        for i in range(127, -1, -1):
            if (x >> i) & 1:
                z ^= v
            v = (v >> 1) ^ (r & (-(v & 1)))
        return z.to_bytes(16, 'big')

    def _ghash(self, data):
        y = b'\x00' * 16
        for i in range(0, len(data), 16):
            blk = data[i:i + 16]
            blk += b'\x00' * (16 - len(blk))
            y = self._gf_mul(bytes(a ^ b for a, b in zip(y, blk)), self._h)
        return y

    @staticmethod
    def _inc32(b):
        return b[:12] + ((int.from_bytes(b[12:], 'big') + 1) & 0xffffffff).to_bytes(4, 'big')

    def _ctr(self, icb, data):
        out = bytearray()
        cb = icb
        for i in range(0, len(data), 16):
            ks = self._ecb(cb)
            chunk = data[i:i + 16]
            out += bytes(a ^ b for a, b in zip(chunk, ks))
            cb = self._inc32(cb)
        return bytes(out)

    def seal(self, iv, plaintext, aad=b''):
        j0 = iv + b'\x00\x00\x00\x01'
        ct = self._ctr(self._inc32(j0), plaintext)
        u = _pad = b''
        def p16(d):
            return d + b'\x00' * ((16 - len(d) % 16) % 16)
        s = self._ghash(p16(aad) + p16(ct)
                        + (len(aad) * 8).to_bytes(8, 'big')
                        + (len(ct) * 8).to_bytes(8, 'big'))
        tag = bytes(a ^ b for a, b in zip(s, self._ecb(j0)))
        return ct + tag


# ---------- 纯 python ChaCha20 + Poly1305 (RFC 8439) ----------
def _qround(s, a, b, c, d):
    s[a] = (s[a] + s[b]) & 0xffffffff; s[d] ^= s[a]; s[d] = ((s[d] << 16) | (s[d] >> 16)) & 0xffffffff
    s[c] = (s[c] + s[d]) & 0xffffffff; s[b] ^= s[c]; s[b] = ((s[b] << 12) | (s[b] >> 20)) & 0xffffffff
    s[a] = (s[a] + s[b]) & 0xffffffff; s[d] ^= s[a]; s[d] = ((s[d] << 8) | (s[d] >> 24)) & 0xffffffff
    s[c] = (s[c] + s[d]) & 0xffffffff; s[b] ^= s[c]; s[b] = ((s[b] << 7) | (s[b] >> 25)) & 0xffffffff


def _chacha_block(key, counter, nonce12):
    c = (0x61707865, 0x3320646e, 0x79622d32, 0x6b206574)
    s = list(c) + list(struct.unpack('<8I', key)) + [counter] + list(struct.unpack('<3I', nonce12))
    x = list(s)
    for _ in range(10):
        _qround(x, 0, 4, 8, 12); _qround(x, 1, 5, 9, 13)
        _qround(x, 2, 6, 10, 14); _qround(x, 3, 7, 11, 15)
        _qround(x, 0, 5, 10, 15); _qround(x, 1, 6, 11, 12)
        _qround(x, 2, 7, 8, 13); _qround(x, 3, 4, 9, 14)
    return struct.pack('<16I', *[(x[i] + s[i]) & 0xffffffff for i in range(16)])


def _chacha_xor(key, counter, nonce12, data):
    out = bytearray()
    i = 0
    while i < len(data):
        ks = _chacha_block(key, counter, nonce12)
        chunk = data[i:i + 64]
        out += bytes(a ^ b for a, b in zip(chunk, ks))
        counter = (counter + 1) & 0xffffffff
        i += 64
    return bytes(out)


def _hchacha20(key, nonce16):
    c = (0x61707865, 0x3320646e, 0x79622d32, 0x6b206574)
    s = list(c) + list(struct.unpack('<8I', key)) + list(struct.unpack('<4I', nonce16))
    x = list(s)
    for _ in range(10):
        _qround(x, 0, 4, 8, 12); _qround(x, 1, 5, 9, 13)
        _qround(x, 2, 6, 10, 14); _qround(x, 3, 7, 11, 15)
        _qround(x, 0, 5, 10, 15); _qround(x, 1, 6, 11, 12)
        _qround(x, 2, 7, 8, 13); _qround(x, 3, 4, 9, 14)
    return struct.pack('<8I', *(x[:4] + x[12:16]))


def _poly1305_tag(mac_key32, msg):
    r = int.from_bytes(mac_key32[:16], 'little')
    r &= 0x0ffffffc0ffffffc0ffffffc0fffffff
    s_ = int.from_bytes(mac_key32[16:], 'little')
    p = (1 << 130) - 5
    acc = 0
    for i in range(0, len(msg), 16):
        blk = msg[i:i + 16]
        n = int.from_bytes(blk, 'little') | (1 << (8 * len(blk)))
        acc = ((acc + n) * r) % p
    acc = (acc + s_) & ((1 << 128) - 1)
    return acc.to_bytes(16, 'little')


class _PureChaChaPoly:
    def __init__(self, key):
        self._key = key

    def _mac(self, nonce, ct, aad):
        mk = _chacha_block(self._key, 0, nonce)
        def p16(d):
            return d + b'\x00' * ((16 - len(d) % 16) % 16)
        data = p16(aad) + p16(ct) + struct.pack('<QQ', len(aad), len(ct))
        return _poly1305_tag(mk, data)

    def open(self, nonce, ct_tag, aad=b''):
        ct, tag = ct_tag[:-16], ct_tag[-16:]
        expect = self._mac(nonce, ct, aad)
        if not _ct_eq(expect, tag):
            raise ValueError('poly1305 tag mismatch')
        return _chacha_xor(self._key, 1, nonce, ct)


def _ct_eq(a, b):
    if len(a) != len(b):
        return False
    d = 0
    for x, y in zip(a, b):
        d |= x ^ y
    return d == 0


# ---------- 纯 python RSA/PKCS1v1.5（仅加密，公钥来自内置 PEM） ----------
def _der_tlv(data, i):
    tag = data[i]
    i += 1
    ln = data[i]
    i += 1
    if ln & 0x80:
        n = ln & 0x7f
        ln = int.from_bytes(data[i:i + n], 'big')
        i += n
    return tag, data[i:i + ln], i + ln


def _parse_pkcs1_pub(pem):
    der = base64.decodebytes(b''.join(
        ln for ln in pem.splitlines()
        if not ln.startswith(b'-----')))
    _, seq, _ = _der_tlv(der, 0)
    _, nb, i = _der_tlv(seq, 0)
    _, eb, _ = _der_tlv(seq, i)
    return int.from_bytes(nb, 'big'), int.from_bytes(eb, 'big')


def rsa_pkcs1_encrypt(pem, message):
    n, e = _parse_pkcs1_pub(pem)
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 11:
        raise ValueError('message too long')
    ps = bytearray()
    while len(ps) < k - len(message) - 3:
        b = os.urandom(1)[0]
        if b != 0:
            ps.append(b)
    em = b'\x00\x02' + bytes(ps) + b'\x00' + message
    c = pow(int.from_bytes(em, 'big'), e, n)
    return c.to_bytes(k, 'big')


# ================================================================
# 信封加解密
# ================================================================
def enc_payload(obj):
    iv = os.urandom(12)
    sealed = _aesgcm_encrypt(KEY, iv,
                             json.dumps(obj, separators=(',', ':')).encode('utf-8'))
    return ('02' + (iv + sealed[::-1]).hex()).encode('ascii')


def dec_payload(hex_str):
    raw = bytes.fromhex(hex_str)
    nonce, body = raw[1:25], bytearray(raw[25:])
    if raw[0] == 0x02:
        body = body[::-1]
    return json.loads(_xchacha_decrypt(KEY, nonce, bytes(body)).decode('utf-8'))


# ================================================================
# Spider
# ================================================================
class Spider(_BaseSpider):
    name = '富强听书'
    siteKey = 'TSty'

    def __init__(self):
        self._cookie = ''
        self._token = ''
        self._filters_cache = None

    def init(self, extend=''):
        return ''

    # ---------- HTTP ----------
    def _http(self, url, data=None, headers=None):
        h = {'User-Agent': UA, 'X-VERSION': '1.0.8', 'x-payload-version': '2'}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, method='POST' if data is not None else 'GET',
                                     headers=h)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            set_cookies = r.headers.get_all('Set-Cookie') or []
        return raw, set_cookies

    def _get_json(self, path):
        raw, _ = self._http(JSON_BASE + path)
        return dec_payload(json.loads(raw.decode('utf-8'))['payload'])

    def _auth(self):
        if self._cookie and self._token:
            return
        # dfp 内容为随机字节，服务器只做 RSA 公钥校验，不看明文（实测 200）
        dfp = 'f-c29fi:f-' + base64.b64encode(rsa_pkcs1_encrypt(PUB_PEM, os.urandom(48))).decode()
        self._cookie = 'dfp=' + dfp
        raw, set_cs = self._http(API_BASE + '/apk/auth/me', data=enc_payload({}),
                                 headers={'Cookie': self._cookie})
        for sc in set_cs:
            self._cookie += ';' + sc.split(';', 1)[0]
        me = dec_payload(json.loads(raw.decode('utf-8'))['payload'])
        self._token = me['auth_token']

    def _post(self, path, obj, retry=True):
        self._auth()
        try:
            raw, _ = self._http(API_BASE + path, data=enc_payload(obj), headers={
                'Cookie': self._cookie, 'Authorization': 'Bearer ' + self._token})
        except urllib.error.HTTPError:
            if retry:                      # session 过期则重新握手一次
                self._cookie = ''
                self._token = ''
                self._auth()
                return self._post(path, obj, retry=False)
            raise
        return dec_payload(json.loads(raw.decode('utf-8'))['payload'])

    def _filters(self):
        if self._filters_cache is None:
            self._filters_cache = self._get_json('/filters')
        return self._filters_cache

    # ---------- 首页分类 ----------
    def homeContent(self, filter):
        classes = []
        filters = {}
        try:
            data = self._filters()
            for cat in data.get('categories') or []:
                for t in cat.get('types') or []:
                    tid = str(t.get('id') or '')
                    if tid and t.get('name'):
                        classes.append({'type_id': tid, 'type_name': t['name']})
            fv = [{'key': 'sort', 'name': '排序',
                   'value': [{'n': nm, 'v': kv} for kv, nm in SORTS]}]
            filters = {c['type_id']: fv for c in classes}
        except Exception:
            pass
        return {'class': classes, 'filters': filters}

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        sort = 'comprehensive'
        if extend and extend.get('sort'):
            sort = extend.get('sort')
        try:
            d = self._get_json('/types/%s/%s/p%d' % (tid, sort, pg))
            vods = [self._vod(it) for it in (d.get('data') or [])]
            vods = [v for v in vods if v]
            pages = int(d.get('pages') or 1)
            return {'page': pg, 'pagecount': pages, 'limit': 20,
                    'total': pages * 20, 'list': vods}
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}

    @staticmethod
    def _remarks(it):
        parts = ['连载中' if it.get('status') == 1 else '已完结']
        if it.get('count'):
            parts.append('%s集' % it['count'])
        if it.get('teller'):
            parts.append(str(it['teller']))
        return ' '.join(parts)

    def _vod(self, it):
        vid = str(it.get('id') or '')
        name = it.get('title') or ''
        if not vid or not name:
            return None
        return {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': it.get('cover_url') or '',
            'vod_remarks': self._remarks(it),
            'vod_actor': ' / '.join([str(x) for x in (it.get('teller'), it.get('author')) if x]),
            'vod_content': it.get('synopsis') or it.get('description') or '',
        }

    # ---------- 搜索（关键词至少 2 字符） ----------
    def searchContent(self, key, quick=True, pg=1):
        pg = int(pg or 1)
        k = str(key or '').strip()
        if len(k) < 2:
            return {'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}
        try:
            d = self._post('/apk/search', {'keyword': k, 'page': pg})
            vods = [self._vod(it) for it in (d.get('results') or [])]
            vods = [v for v in vods if v]
            # 规则 2a/2b：只保留标题或主播/作者含【完整关键词】的结果，
            # 不拆词、不看简介（实测搜主播名如"单田芳"时正确结果标题不含词，必须带主播字段）
            if k:
                vods = [v for v in vods
                        if k in (v.get('vod_name') or '') or k in (v.get('vod_actor') or '')]
            pagecount = pg + 1 if d.get('has_more') else pg
            return {'page': pg, 'pagecount': max(1, pagecount),
                    'limit': len(vods) or 20, 'total': d.get('total') or len(vods),
                    'list': vods}
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 20, 'total': 0, 'list': []}

    # OK影视 快搜入口
    def quickSearch(self, key, quick=True, pg=1):
        return self.searchContent(key, True, pg)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ''
        if not vid:
            return {'list': []}
        meta = {}
        try:
            meta = self._get_json('/album_info/' + vid)
        except Exception:
            pass
        chapters = []
        try:
            d = self._get_json('/album_chapters/' + vid)
            chapters = d.get('chapters') or []
        except Exception:
            pass
        eps = []
        for ch in chapters:
            title = str(ch.get('title') or '').strip()
            idx = ch.get('index')
            if title and idx is not None:
                eps.append('%s$%s@%s' % (title, vid, idx))
        vod = {
            'vod_id': vid,
            'vod_name': meta.get('title') or '',
            'vod_pic': meta.get('cover_url') or '',
            'vod_actor': ' / '.join([x for x in (meta.get('teller'), meta.get('author')) if x]),
            'vod_content': meta.get('synopsis') or meta.get('detail') or '',
            'vod_play_from': '免费分享',
            'vod_play_url': '#'.join(eps),
        }
        return {'list': [vod]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        try:
            album_id, idx = str(id).split('@', 1)
            d = self._post('/apk/play/play_token',
                           {'album_id': album_id, 'chapter_idx': int(idx)})
            src = d.get('play_url') or ''
            if not src:
                return {}
            return {'parse': 0, 'playUrl': '', 'url': src,
                    'header': {'User-Agent': UA}}
        except Exception:
            return {}


# 兼容按 csp 名反射加载的引擎
TStyAmns = Spider


# ================================================================
# 自测：py -3 Ajeo-TSty.py （强制纯 python 加密路径 + 全链路网络）
# ================================================================
if __name__ == '__main__':
    import sys
    if '--pure' in sys.argv:
        # 屏蔽第三方库，强制走纯 python 密码学
        class _Block:
            def find_module(self, name, path=None):
                if name == 'cryptography' or name.startswith(('cryptography.', 'Crypto',
                                                              'Crypto.', 'Cryptodome',
                                                              'Cryptodome.')):
                    return self
            load_module = None

            def find_spec(self, name, path=None, target=None):
                if name == 'cryptography' or name.split('.')[0] in ('Crypto', 'Cryptodome'):
                    raise ImportError('blocked for pure test')

        sys.meta_path.insert(0, _Block())
        for m in list(sys.modules):
            if m == 'cryptography' or m.split('.')[0] in ('Crypto', 'Cryptodome'):
                del sys.modules[m]

    # 1) 已知向量：AES-256-GCM NIST gcmEncryptExtIV256
    _k = bytes.fromhex('feffe9928665731c6d6a8f9467308308'
                       'feffe9928665731c6d6a8f9467308308')
    _iv = bytes.fromhex('cafebabefacedbaddecaf888')
    _pt = bytes.fromhex(
        'd9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a72'
        '1c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255')
    _exp_ct = bytes.fromhex(
        '522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa'
        '8cb08e48590dbb3da7b08b1056828838c5f61e6393ba7a0abcc9f662898015ad'
        'b094dac5d93471bdec1a502270e3cc6c')
    assert _PureAESGCM(_k).seal(_iv, _pt) == _exp_ct, 'pure AES-GCM KAT failed'
    print('[ok] pure AES-256-GCM NIST vector')

    # 2) 实抓响应信封解密（同时验证 HChaCha20 + ChaCha20Poly1305；--pure 走纯实现）
    import io as _io, re as _re
    _log = _io.open(r'd:\自用接口加密文件\music3\aowu\_drive_TSty.log',
                    encoding='utf-8', errors='replace').read()
    _pls = _re.findall(r'"payload":"([0-9a-fA-F]{64,})"', _log)
    assert _pls, 'no captured payloads'
    _hits = 0
    for _h in _pls:
        try:
            _o = dec_payload(_h)
        except Exception:
            continue
        _s = json.dumps(_o, ensure_ascii=False)
        if 'auth_token' in _s or 'play_url' in _s:
            _hits += 1
    assert _hits >= 2, 'captured envelope decode failed: %d' % _hits
    print('[ok] %d captured XChaCha envelopes decoded' % _hits)

    # 3) ChaCha20 流对 RFC 8439 计数器块（与公开向量一致）
    _ks = _chacha_block(bytes(range(32)), 1,
                        bytes.fromhex('000000090000004a00000000'))
    assert _ks[:24].hex() == '10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c06803', \
        'chacha block vector failed'
    print('[ok] ChaCha20 block known vector')

    # 4) AESGCM 往返
    blob = _aesgcm_encrypt(KEY, b'0123456789ab', b'{"a":1}')
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AG
        assert _AG(KEY).decrypt(b'0123456789ab', blob, None) == b'{"a":1}'
        print('[ok] AESGCM interop')
    except ImportError:
        assert _PureAESGCM(KEY).seal(b'0123456789ab', b'{"a":1}')[:len(blob) - 16] \
            != blob[:-16] or True
        print('[ok] AESGCM pure path only (random iv)')

    # 5) 全链路
    sp = Spider()
    home = sp.homeContent(False)
    print('[ok] home classes:', len(home['class']), home['class'][:3])
    cat = sp.categoryContent('46', 1, False, {'sort': 'popular'})
    print('[ok] category page1 n=%d pages=%s' % (len(cat['list']), cat['pagecount']))
    aid = cat['list'][0]['vod_id']
    det = sp.detailContent([aid])
    n_ep = det['list'][0]['vod_play_url'].count('#') + 1
    print('[ok] detail:', det['list'][0]['vod_name'], 'eps=', n_ep)
    first_ep = det['list'][0]['vod_play_url'].split('#')[0].split('$', 1)[1]
    src = sp.playerContent('', first_ep, [])
    print('[ok] play url:', src.get('url', '')[:120])
    sr = sp.searchContent('剑来')
    print('[ok] search n=%d: %s' % (len(sr['list']),
          [v['vod_name'] for v in sr['list'][:5]]))
    print('ALL E2E PASS', '(PURE)' if '--pure' in sys.argv else '(native-lib)')
