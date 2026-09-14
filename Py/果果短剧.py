# -*- coding: utf-8 -*-
# 果果短剧 - 独立可用版
# 来源: aidaox-20260829.jar csp_GuoGuo（已解密去混淆, 签名/ECDH/解密全链路实测通过）
# 兼容: OK影视 / 影视仓（TVBox Python 引擎）
# 数据: 字节跳动短剧 fqnovel API（无签名列表/搜索, 签名剧集/播放参数）
# 签名: 作者签名服务器 https://jk.catvod.site/jk/hg (HMAC-SHA256) + ECDH P-256 + AES-GCM 派生播放key
# 播放: CDN MP4 (CENC AES-CTR 加密) -> 本地代理解密后输出
# 依赖: requests + cryptography（OK影视/影视仓 Python 引擎自带）

from base.spider import Spider
import requests
import base64
import hashlib
import hmac
import json
import re
import struct
import time
import uuid
import urllib.parse

# ---------------- cryptography 探测 + 纯 Python 加密回退 ----------------
try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    _HAS_CRYPTOGRAPHY = True
except Exception:
    _HAS_CRYPTOGRAPHY = False
import sys as _sys
_sys.stderr.write('GUOGUO init CRYPTO=%s\n' % _HAS_CRYPTOGRAPHY)


def _p_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        xt = ((p << 1) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        p = p ^ xt
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q ^= 0x09 if q & 0x80 else 0
        q &= 0xFF
        s = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) ^ \
            ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (s ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


_p_SBOX = _p_sbox()


def _p_xt(x):
    return ((x << 1) ^ (0x1B if x & 0x80 else 0)) & 0xFF


def _p_aes_enc_block(key, block):
    sbox = _p_SBOX
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[i * 4:(i + 1) * 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [sbox[b] for b in t]
            t[0] ^= rcon
            rcon = _p_xt(rcon)
        elif nk > 6 and i % nk == 4:
            t = [sbox[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    st = [[block[r + 4 * c] for c in range(4)] for r in range(4)]

    def add_rk(rnd):
        for r in range(4):
            for c in range(4):
                st[r][c] ^= w[rnd * 4 + c][r]

    add_rk(0)
    for rnd in range(1, nr + 1):
        for r in range(4):
            for c in range(4):
                st[r][c] = sbox[st[r][c]]
        for r in range(4):
            st[r] = st[r][r:] + st[r][:r]
        if rnd != nr:
            for c in range(4):
                b0, b1, b2, b3 = st[0][c], st[1][c], st[2][c], st[3][c]
                st[0][c] = _p_xt(b0) ^ (_p_xt(b1) ^ b1) ^ b2 ^ b3
                st[1][c] = b0 ^ _p_xt(b1) ^ (_p_xt(b2) ^ b2) ^ b3
                st[2][c] = b0 ^ b1 ^ _p_xt(b2) ^ (_p_xt(b3) ^ b3)
                st[3][c] = (_p_xt(b0) ^ b0) ^ b1 ^ b2 ^ _p_xt(b3)
        add_rk(rnd)
    out = bytearray(16)
    for r in range(4):
        for c in range(4):
            out[r + 4 * c] = st[r][c]
    return bytes(out)


def _p_aes_ctr(key, iv, data):
    out = bytearray()
    counter = int.from_bytes(iv, 'big')
    for i in range(0, len(data), 16):
        ks = _p_aes_enc_block(key, counter.to_bytes(16, 'big'))
        out += bytes(a ^ b for a, b in zip(data[i:i + 16], ks))
        counter = (counter + 1) & ((1 << 128) - 1)
    return bytes(out)


def _p_rev128(x):
    x = (x >> 64) | (x << 64)
    x = ((x >> 32) & 0x00000000FFFFFFFF00000000FFFFFFFF) | ((x & 0x00000000FFFFFFFF00000000FFFFFFFF) << 32)
    x = ((x >> 16) & 0x0000FFFF0000FFFF0000FFFF0000FFFF) | ((x & 0x0000FFFF0000FFFF0000FFFF0000FFFF) << 16)
    x = ((x >> 8) & 0x00FF00FF00FF00FF00FF00FF00FF00FF) | ((x & 0x00FF00FF00FF00FF00FF00FF00FF00FF) << 8)
    x = ((x >> 4) & 0x0F0F0F0F0F0F0F0F0F0F0F0F0F0F0F0F) | ((x & 0x0F0F0F0F0F0F0F0F0F0F0F0F0F0F0F0F) << 4)
    x = ((x >> 2) & 0x33333333333333333333333333333333) | ((x & 0x33333333333333333333333333333333) << 2)
    x = ((x >> 1) & 0x55555555555555555555555555555555) | ((x & 0x55555555555555555555555555555555) << 1)
    return x & ((1 << 128) - 1)


def _p_gf_mul(x, y):
    z = 0
    mask = (1 << 128) - 1
    for _ in range(128):
        if y & 1:
            z ^= x
        x = ((x << 1) ^ (0x87 if x >> 127 else 0)) & mask
        y >>= 1
    return z


def _p_ghash(h_bytes, data):
    H = _p_rev128(int.from_bytes(h_bytes, 'big'))
    y = 0
    for i in range(0, len(data), 16):
        v = _p_rev128(int.from_bytes(data[i:i + 16].ljust(16, b'\x00'), 'big'))
        y = _p_gf_mul(y ^ v, H)
    return _p_rev128(y).to_bytes(16, 'big')


def _p_gcm_decrypt(key, nonce, ct_tag):
    h = _p_aes_enc_block(key, b'\x00' * 16)
    j0 = int.from_bytes(nonce + b'\x00\x00\x00\x01', 'big')
    tag_mask = _p_aes_enc_block(key, j0.to_bytes(16, 'big'))
    ct = ct_tag[:-16]
    tag = ct_tag[-16:]
    out = _p_aes_ctr(key, (j0 + 1).to_bytes(16, 'big'), ct)
    data = (ct.ljust((len(ct) + 15) // 16 * 16, b'\x00') if ct else b'')
    data += (0).to_bytes(8, 'big') + (len(ct) * 8).to_bytes(8, 'big')
    expect = (int.from_bytes(_p_ghash(h, data), 'big') ^ int.from_bytes(tag_mask, 'big')).to_bytes(16, 'big')
    if expect != tag:
        raise ValueError('GCM tag mismatch')
    return out


_p_P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
_p_A = 0xffffffff00000001000000000000000000000000fffffffffffffffffffffffc
_p_G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
        0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)


def _p_point_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _p_P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + _p_A) * pow(2 * y1 % _p_P, _p_P - 2, _p_P) % _p_P
    else:
        lam = (y2 - y1) * pow((x2 - x1) % _p_P, _p_P - 2, _p_P) % _p_P
    x3 = (lam * lam - x1 - x2) % _p_P
    y3 = (lam * (x1 - x3) - y1) % _p_P
    return (x3, y3)


def _p_point_mul(k, p):
    r = None
    while k:
        if k & 1:
            r = _p_point_add(r, p)
        p = _p_point_add(p, p)
        k >>= 1
    return r


def _p_der_len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(b)]) + b


def _p_der_seq(body):
    return b'\x30' + _p_der_len(len(body)) + body


def _p_spki(pub):
    point = b'\x04' + pub[0].to_bytes(32, 'big') + pub[1].to_bytes(32, 'big')
    ec_oid = b'\x06\x07\x2a\x86\x48\xce\x3d\x02\x01'
    alg = b'\x06\x08\x2a\x86\x48\xce\x3d\x03\x01\x07'
    return _p_der_seq(_p_der_seq(ec_oid + alg) + b'\x03' + bytes([len(point) + 1]) + b'\x00' + point)


def _p_parse_spki(der):
    i = der.find(b'\x04')
    if i < 0 or i + 65 > len(der):
        raise ValueError('bad spki')
    return (int.from_bytes(der[i + 1:i + 33], 'big'),
            int.from_bytes(der[i + 33:i + 65], 'big'))


def _p_derive(spade_a):
    """纯 Python 版 key 派生: ECDH P-256 + SHA256 + AES-GCM 解密"""
    import os as _os
    priv = int.from_bytes(_os.urandom(32), 'big') % (_p_P - 1) + 1
    pub = _p_point_mul(priv, _p_G)
    pub_b64 = base64.b64encode(_p_spki(pub)).decode()
    j = _post_signed('/v1/derive', {'spade_a': spade_a, 'client_pub': pub_b64})
    server_pub, key_enc = j.get('server_pub'), j.get('key_enc')
    if not server_pub or not key_enc:
        return None
    srv = _p_parse_spki(base64.b64decode(server_pub))
    shared = _p_point_mul(priv, srv)
    if shared is None:
        return None
    aeskey = hashlib.sha256(shared[0].to_bytes(32, 'big')).digest()
    enc = base64.b64decode(key_enc)
    plain = _p_gcm_decrypt(aeskey, enc[:12], enc[12:])
    return plain.hex()

# ---------------- 常量 ----------------
HMAC_KEY = bytes.fromhex('203611e7fbb53a20b5e87164ea59dfb7505d4032eb5f810f6827676f40cdd8cc')
SIGN_HOST = 'https://jk.catvod.site/jk/hg'
UA = 'com.phoenix.read/72732 (Linux; U; Android 13; zh_CN; Mi 10; Build/TKQ1.221114.001)'
HOSTS = ['https://api5-normal-sinfonlineb.fqnovel.com', 'https://api5-normal.fqnovel.com',
         'https://api5-normal-sinfonlinec.fqnovel.com', 'https://reading.snssdk.com']
DEVICE_ID = '1677186774376987'
IID = '4351204728771643'
CATES = [
    ('short_play', '短剧'), ('comic_series', '动漫短剧'), ('ai_series', 'AI短剧'),
]


# ---------------- 本地代理端口探测 ----------------
_PROXY_PORT = None


def _proxy_port():
    global _PROXY_PORT
    if _PROXY_PORT:
        return _PROXY_PORT
    try:
        import socket
        for p in (1314, 9978):
            try:
                s = socket.create_connection(('127.0.0.1', p), timeout=0.5)
                s.settimeout(0.5)
                s.sendall(b'GET /proxy?do=test HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n')
                try:
                    head = s.recv(200).decode('utf-8', 'ignore')
                except Exception:
                    head = ''
                s.close()
                if head and '404' not in head and 'Attempt' not in head \
                        and 'Exception' not in head and 'Error' not in head:
                    _PROXY_PORT = p
                    return p
            except Exception:
                continue
    except Exception:
        pass
    _PROXY_PORT = 1314
    return _PROXY_PORT


# ---------------- 内置本地 HTTP 代理（不依赖壳的 Server，随机端口） ----------------
_LOCAL_SRV = {'port': 0}


def _java_dl(u, host, tmo):
    """Chaquopy 桥接 Java HttpURLConnection 下载——Java TLS 栈(JSSE/okhttp)与 Python 不同，
    可绕过字节 CDN 对 Python 指纹的黑洞。不可用时抛异常由调用方回退 requests。"""
    from java.net import URL, HttpURLConnection
    from java.io import ByteArrayOutputStream
    conn = URL(u).openConnection()
    conn.setConnectTimeout(int(tmo * 1000))
    conn.setReadTimeout(int(tmo * 1000))
    conn.setRequestProperty('User-Agent', UA)
    conn.setRequestProperty('Referer', 'https://www.douyin.com/')
    if host:
        conn.setRequestProperty('Host', host)
    conn.setInstanceFollowRedirects(True)
    code = conn.getResponseCode()
    if code != 200:
        raise RuntimeError('java dl http %s' % code)
    inp = conn.getInputStream()
    out = ByteArrayOutputStream()
    buf = [0] * 8192
    while True:
        n = inp.read(buf, 0, 8192)
        if n < 0:
            break
        out.write(buf, 0, n)
    inp.close()
    return bytes(out.toByteArray())


def _dl_mp4(murl, timeout=20):
    """多 IP 探针 + Range 分段并发下载 MP4。
    真机现象：单连接下载被 CDN 限速 ~0.6MB/s（24MB 需 80s+，播放器等不起）；
    本实现先并发探测各节点首 1MB（Range 206）选出最快 IP，再 8 段并发下载（总 ~5MB/s）。
    探测/分段结果均打印 stderr，便于真机定位。"""
    import socket as _sk, threading as _th, time as _t, sys as _sys, re as _re
    from requests.adapters import HTTPAdapter
    s = requests.Session()
    s.mount('https://', HTTPAdapter(max_retries=0))  # 关自动重试（重试会白等 45s）
    p = urllib.parse.urlparse(murl)
    host = p.netloc
    # 候选池：本地/真机历史验证过的 CDN 节点（多子域共用，跨子域 403 的会快速失败无妨）
    ips = ['49.79.240.200', '49.79.240.181', '111.172.211.172', '111.172.211.163',
           '223.244.13.62', '124.72.136.184', '124.72.136.168', '183.136.160.5',
           '111.172.236.82', '61.170.68.69', '222.186.163.48']
    try:
        for i in _sk.getaddrinfo(host, 443, _sk.AF_INET):
            ip = i[4][0]
            if ip not in ips:
                ips.append(ip)
    except Exception as e:
        print('DL getaddrinfo fail', repr(e)[:80], file=_sys.stderr)
    print('DL host', host, 'ips', ips, file=_sys.stderr)
    if not ips:
        ips = [host]

    def _probe(ip, res):
        t0 = _t.time()
        try:
            u2 = urllib.parse.urlunparse(('https', ip, p.path, p.params, p.query, p.fragment))
            r = s.get(u2, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/', 'Host': host,
                                   'Range': 'bytes=0-1048575'}, timeout=8, verify=False)
            r.raise_for_status()
            total = None
            mm = _re.search(r'/(\d+)\s*$', r.headers.get('Content-Range') or '')
            if mm:
                total = int(mm.group(1))
            print('DL probe ok', ip, len(r.content), '%.1fs' % (_t.time() - t0), 'total', total, file=_sys.stderr)
            res.setdefault('probes', []).append((_t.time() - t0, ip, total))
        except Exception as e:
            print('DL probe fail', ip, type(e).__name__, str(e)[:50], '%.1fs' % (_t.time() - t0), file=_sys.stderr)

    res = {}
    ths = [_th.Thread(target=_probe, args=(ip, res), daemon=True) for ip in ips]
    for t in ths:
        t.start()
    for t in ths:
        t.join(12)
    probes = sorted(res.get('probes', []))
    if not probes:
        # 所有节点 8s 内都连不上（连接层黑洞）→ 单线程全量试一次（关重试）
        for ip in ips:
            try:
                u2 = urllib.parse.urlunparse(('https', ip, p.path, p.params, p.query, p.fragment))
                r = s.get(u2, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/', 'Host': host},
                          timeout=timeout, verify=False)
                r.raise_for_status()
                print('DL full', ip, len(r.content), file=_sys.stderr)
                return r.content
            except Exception as e:
                print('DL full fail', ip, type(e).__name__, str(e)[:50], file=_sys.stderr)
        raise RuntimeError('mp4 download failed (no reachable node)')
    best_ip, total = probes[0][1], probes[0][2]
    print('DL best', best_ip, 'total', total, file=_sys.stderr)
    if not total or total <= 1048576:
        # Range 不支持（回 200 全量）→ 直接全量下载
        u2 = urllib.parse.urlunparse(('https', best_ip, p.path, p.params, p.query, p.fragment))
        r = s.get(u2, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/', 'Host': host},
                  timeout=timeout, verify=False)
        r.raise_for_status()
        print('DL full2', best_ip, len(r.content), file=_sys.stderr)
        return r.content
    # 8 段并发
    n = 8
    step = (total + n - 1) // n
    segs = [None] * n

    def _seg(i):
        st, en = i * step, min((i + 1) * step - 1, total - 1)
        if st > en:
            segs[i] = b''
            return
        t0 = _t.time()
        try:
            u2 = urllib.parse.urlunparse(('https', best_ip, p.path, p.params, p.query, p.fragment))
            r = s.get(u2, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/', 'Host': host,
                                   'Range': 'bytes=%d-%d' % (st, en)}, timeout=timeout, verify=False)
            r.raise_for_status()
            segs[i] = r.content
            print('DL seg', i, len(r.content), '%.1fs' % (_t.time() - t0), file=_sys.stderr)
        except Exception as e:
            print('DL seg fail', i, type(e).__name__, str(e)[:50], '%.1fs' % (_t.time() - t0), file=_sys.stderr)

    ths = [_th.Thread(target=_seg, args=(i,), daemon=True) for i in range(n)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout + 5)
    if all(x is not None for x in segs):
        body = b''.join(segs)
        print('DL merged', len(body), 'expected', total, file=_sys.stderr)
        return body
    # 缺失段重试一轮
    for i in range(n):
        if segs[i] is None:
            st, en = i * step, min((i + 1) * step - 1, total - 1)
            if st > en:
                continue
            try:
                u2 = urllib.parse.urlunparse(('https', best_ip, p.path, p.params, p.query, p.fragment))
                r = s.get(u2, headers={'User-Agent': UA, 'Referer': 'https://www.douyin.com/', 'Host': host,
                                       'Range': 'bytes=%d-%d' % (st, en)}, timeout=timeout, verify=False)
                r.raise_for_status()
                segs[i] = r.content
                print('DL seg retry ok', i, file=_sys.stderr)
            except Exception as e:
                print('DL seg retry fail', i, str(e)[:50], file=_sys.stderr)
    if all(x is not None for x in segs):
        body = b''.join(segs)
        print('DL merged2', len(body), 'expected', total, file=_sys.stderr)
        return body
    raise RuntimeError('segmented download incomplete')


_SRV_CACHE = {'k': '', 'body': None}


_SRV_CACHE = {'k': '', 'body': None}


def _proxy_handle(c):
    import sys
    try:
        c.settimeout(60)
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = c.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 65536:
                break
        head = data.split(b'\r\n\r\n')[0].decode('utf-8', 'ignore')
        line = head.split('\r\n')[0] if head else ''
        parts = line.split(' ')
        path = parts[1] if len(parts) > 1 else '/'
        q = urllib.parse.parse_qs(path.split('?', 1)[1]) if '?' in path else {}
        u = (q.get('url') or [''])[0]
        k = (q.get('key') or [''])[0]
        rng = ''
        for hl in head.split('\r\n'):
            if hl.lower().startswith('range:'):
                rng = hl.split(':', 1)[1].strip()
        if not u:
            c.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            return
        main_url = base64.b64decode(u).decode() if not u.startswith('http') else u
        key = base64.b64decode(k).decode()
        ck = main_url + '|' + key
        if _SRV_CACHE['k'] == ck and _SRV_CACHE['body'] is not None:
            body = _SRV_CACHE['body']
            print('SRV cache hit', len(body), file=sys.stderr)
        else:
            t0 = time.time()
            dl = _dl_mp4(main_url)
            print('SRV dl', len(dl), '%.1fs' % (time.time() - t0), file=sys.stderr)
            t0 = time.time()
            body = cenc_decrypt(dl, key)
            print('SRV dec', len(body), '%.1fs' % (time.time() - t0), file=sys.stderr)
            t0 = time.time()
            body = _clean_csd(body)
            print('SRV clean', len(body), '%.1fs' % (time.time() - t0),
                  'ByteVC', b'ByteVC' in body, file=sys.stderr)
            _SRV_CACHE['k'] = ck
            _SRV_CACHE['body'] = body
        if rng:
            m = re.match(r'bytes=(\d*)-(\d*)', rng)
            if m:
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else len(body) - 1
                end = min(end, len(body) - 1)
                if start >= len(body):
                    c.sendall(b'HTTP/1.1 416 Range Not Satisfiable\r\nContent-Range: bytes */%d\r\nContent-Length: 0\r\nConnection: close\r\n\r\n' % len(body))
                    return
                part = body[start:end + 1]
                resp = b'HTTP/1.1 206 Partial Content\r\nContent-Type: video/mp4\r\nAccept-Ranges: bytes\r\n' + \
                    ('Content-Range: bytes %d-%d/%d\r\nContent-Length: %d\r\nConnection: close\r\n\r\n' %
                     (start, end, len(body), len(part))).encode() + part
                print('SRV range', start, end, len(part), file=sys.stderr)
                c.sendall(resp)
                return
        resp = b'HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nAccept-Ranges: bytes\r\nContent-Length: ' + \
            str(len(body)).encode() + b'\r\nConnection: close\r\n\r\n' + body
        print('SRV 200', len(body), file=sys.stderr)
        c.sendall(resp)
    except Exception as e:
        print('SRV ERR', type(e).__name__, str(e)[:80], file=sys.stderr)
        try:
            c.sendall(b'HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        except Exception:
            pass
    finally:
        try:
            c.close()
        except Exception:
            pass


def _ensure_server():
    """启动内置 HTTP server（随机端口），返回端口；失败返回 0。"""
    if _LOCAL_SRV['port']:
        return _LOCAL_SRV['port']
    try:
        import socket as _sk, threading as _th
        srv = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
        srv.setsockopt(_sk.SOL_SOCKET, _sk.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        _LOCAL_SRV['port'] = port

        def _loop():
            while True:
                try:
                    conn, _ = srv.accept()
                except Exception:
                    break
                try:
                    _th.Thread(target=_proxy_handle, args=(conn,), daemon=True).start()
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass

        _th.Thread(target=_loop, daemon=True).start()
        return port
    except Exception:
        return 0


# ---------------- HTTP 基础 ----------------
def _http(url, data=None, headers=None, timeout=20):
    r = requests.post(url, data=data, headers=headers or {}, timeout=timeout) if data is not None \
        else requests.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.content


def _device_query():
    p = {'device_id': DEVICE_ID, 'iid': IID, 'aid': '8662', 'app_name': 'novelread',
         'version_code': '72732', 'version_name': '7.2.7.32', 'device_platform': 'android',
         'os': 'android', 'ssmix': 'a', 'device_type': 'Mi 10', 'device_brand': 'Xiaomi',
         'language': 'zh', 'os_api': '33', 'os_version': '13', 'manifest_version_code': '72732',
         'resolution': '1080*2206', 'dpi': '440', 'update_version_code': '72732',
         '_rticket': str(int(time.time() * 1000)), 'host_abi': 'arm64-v8a',
         'dragon_device_type': 'phone', 'channel': 'update_64', 'ac': 'wifi', 'cdid': str(uuid.uuid4())}
    return urllib.parse.urlencode(p)


def _device_query_for_sign():
    q = [('aid', '8662'), ('device_platform', 'android'), ('os_version', '13'), ('version_code', '72732'),
         ('version_name', '7.2.7.32'), ('update_version_code', '72732'), ('app_name', 'novelread'),
         ('channel', 'seo_laxin_pc_android'), ('device_id', DEVICE_ID), ('iid', IID),
         ('device_type', 'Mi 10'), ('device_brand', 'Xiaomi'), ('language', 'zh'),
         ('resolution', '1080*2206'), ('dpi', '440'), ('host_abi', 'arm64-v8a'), ('dragon_device_type', 'phone')]
    return urllib.parse.urlencode(q)


def _hmac_sign(method, path, body_bytes, ts, nonce):
    msg = ('%s|%s|%s|%d|%s' % (method, path, hashlib.sha256(body_bytes).hexdigest(), ts, nonce)).encode()
    return hmac.new(HMAC_KEY, msg, hashlib.sha256).hexdigest()


def _post_signed(path, body_obj):
    data = json.dumps(body_obj, separators=(',', ':')).encode()
    ts = int(time.time())
    nonce = str(uuid.uuid4())
    headers = {
        'Content-Type': 'application/json', 'X-App-Id': 'guoguo-t4',
        'X-App-Ts': str(ts), 'X-App-Nonce': nonce, 'X-App-Sign': _hmac_sign('POST', path, data, ts, nonce)}
    r = requests.post(SIGN_HOST + path, data=data, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def _fqnovel_post(path, body_obj):
    body_str = json.dumps(body_obj, separators=(',', ':')).replace(' ', '')
    md5u = hashlib.md5(body_str.encode()).hexdigest().upper()
    query = _device_query_for_sign()
    ts = int(time.time())
    sg = _post_signed('/v1/sign', {'query': query, 'body_md5': md5u, 'cookie': '', 'khronos': str(ts)})
    xg = sg.get('x_gorgon') or ''
    xk = sg.get('x_khronos') or str(ts)
    if not xg:
        return None
    headers = {'User-Agent': UA, 'Content-Type': 'application/json; charset=utf-8', 'Accept': 'application/json',
               'x-ss-dp': '8662', 'x-ss-stub': md5u, 'X-Gorgon': xg, 'X-Khronos': xk}
    last = None
    for host in HOSTS:
        try:
            return json.loads(_http(host + path + '?' + query, body_str.encode(), headers))
        except Exception as e:
            last = e
    raise last


# ---------------- 数据接口 ----------------
def _landpage(genre, offset, limit=18):
    body = {'filter_ids': '', 'req_scene': 'default', 'offset': offset, 'need_selector_panel': False,
            'limit': limit,
            'select_items': {'category_dim_epoch': [], 'online_time': [], 'gender': [],
                             'category_dim_role': [], 'genre': [genre], 'sort': [], 'category_dim_theme': []},
            'session_id': '', 'req_type': 'only_content', 'client_req_type': 1}
    url = HOSTS[0] + '/reading/distribution/category/landpage/v1/?' + _device_query()
    data = _http(url, json.dumps(body, separators=(',', ':')).encode(),
                 {'User-Agent': UA, 'Content-Type': 'application/json', 'Accept': 'application/json', 'x-ss-dp': '8662'})
    return json.loads(data)


def _extract_videos(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        # 新接口结构: series_id + title + video_data[0].vid（vid 在嵌套数组里）
        if ('series_id' in obj and ('title' in obj or 'book_name' in obj)
                and isinstance(obj.get('video_data'), list) and obj['video_data']):
            _vd0 = obj['video_data'][0]
            if isinstance(_vd0, dict):
                _vv = _vd0.get('vid') or _vd0.get('video_id') or ''
                if _vv:
                    _cp = dict(obj)
                    _cp['vid'] = _vv
                    out.append(_cp)
        # 旧接口结构: series_id + title + vid/video_id 同层
        if 'series_id' in obj and 'title' in obj and ('vid' in obj or 'video_id' in obj):
            out.append(obj)
        for v in obj.values():
            _extract_videos(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _extract_videos(v, out)
    return out


def _episode_vids(series_id, vid):
    j = _fqnovel_post('/novel/player/video_detail/v1/',
                      {'series_id': series_id, 'vid': vid, 'content_type': 1})
    if not j or j.get('code') != 0:
        return []
    vl = ((j.get('data') or {}).get('video_data') or {}).get('video_list') or []
    items = []
    for i, it in enumerate(vl):
        v = it.get('vid') or it.get('video_id') or ''
        if v and re.match(r'^\d+$', v):
            items.append((it.get('vid_index') or (i + 1), v))
    items.sort(key=lambda x: x[0])
    return [v for _, v in items]


def _search_cue(keyword):
    """搜索联想词（data.text + data_v1[0..2]，最多3个）"""
    q = urllib.parse.urlencode({'query': keyword})
    url = HOSTS[0] + '/reading/bookapi/search/cue/v?' + _device_query() + '&' + q
    data = _http(url, headers={'User-Agent': UA, 'Accept': 'application/json', 'x-ss-dp': '8662'})
    j = json.loads(data)
    words = []
    d = j.get('data') or {}
    if d.get('text'):
        words.append(d['text'])
    for it in (j.get('data_v1') or [])[:3]:
        if len(words) >= 3:
            break
        if it.get('text'):
            words.append(it['text'])
    return words


def _search_landing(keyword, offset=0, count=20):
    q = urllib.parse.urlencode({'query': keyword, 'offset': str(offset), 'count': str(count)})
    url = HOSTS[0] + '/reading/bookapi/search/schema_landing/v?' + _device_query() + '&' + q
    data = _http(url, headers={'User-Agent': UA, 'Accept': 'application/json', 'x-ss-dp': '8662'})
    return json.loads(data)


def _search(keyword):
    """完整搜索：cue 联想词(≤3) -> schema_landing；不足12条补原文/原文+短剧"""
    words = _search_cue(keyword)
    if not words:
        words.append(keyword)
        if '短剧' not in keyword:
            words.append(keyword + '短剧')
    out = []
    seen = set()
    for w in words:
        if len(out) >= 12:
            break
        try:
            j = _search_landing(w)
        except Exception:
            continue
        for v in _extract_videos(j):
            sid = v.get('series_id')
            if sid and sid not in seen:
                out.append(v)
                seen.add(sid)
    # 兜底：补搜原文
    if len(out) < 12 and keyword not in words:
        try:
            j = _search_landing(keyword)
            for v in _extract_videos(j):
                sid = v.get('series_id')
                if sid and sid not in seen:
                    out.append(v)
                    seen.add(sid)
        except Exception:
            pass
    return out


def _video_model(vid):
    body = {'biz_param': {'detail_page_version': 0, 'device_level': 3, 'disable_digg_stat': False,
                          'disable_video_relate_book': False, 'from_video_id': '',
                          'need_all_video_definition': True, 'need_mp4_align': False,
                          'use_os_player': False, 'use_server_dns': True,
                          'use_server_dns_scene': 'cold_start_stage', 'video_platform': 0},
            'content_type': 1, 'video_id': vid}
    j = _fqnovel_post('/novel/player/video_model/v1/', body)
    if not j or j.get('code') != 0:
        return None
    vm = (j.get('data') or {}).get('video_model')
    if isinstance(vm, str):
        try:
            vm = json.loads(vm)
        except Exception:
            return None
    return vm or None


def _decode_main_url(s):
    s = (s or '').strip()
    if s.startswith('//'):
        return 'https:' + s
    if s.startswith('http://') or s.startswith('https://'):
        return s
    try:
        s = base64.b64decode(s).decode().strip()
    except Exception:
        return ''
    if s.startswith('//'):
        return 'https:' + s
    return s if s.startswith('http') else ''


def _derive_key(spade_a):
    if not _HAS_CRYPTOGRAPHY:
        return _p_derive(spade_a)
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    priv = ec.generate_private_key(ec.SECP256R1())
    pub_b64 = base64.b64encode(priv.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    j = _post_signed('/v1/derive', {'spade_a': spade_a, 'client_pub': pub_b64})
    server_pub, key_enc = j.get('server_pub'), j.get('key_enc')
    if not server_pub or not key_enc:
        return None
    srv = load_der_public_key(base64.b64decode(server_pub))
    shared = priv.exchange(ec.ECDH(), srv)
    aeskey = hashlib.sha256(shared).digest()
    enc = base64.b64decode(key_enc)
    plain = AESGCM(aeskey).decrypt(enc[:12], enc[12:], None)
    return plain.hex()


# ---------------- MP4 CENC 解密 (GuoGuoCenc 移植) ----------------
_CONTAINER = {'moov', 'trak', 'mdia', 'minf', 'stbl', 'sinf', 'schi'}


def _u(data, off, n):
    v = 0
    for i in range(n):
        v = (v << 8) | (data[off + i] & 0xFF)
    return v


def _typ(data, off):
    return ''.join(chr(data[off + i] & 0xFF) for i in range(4))


def _parse(data, start, end):
    boxes = []
    pos = start
    while pos + 8 <= end:
        size = _u(data, pos, 4)
        typ = _typ(data, pos + 4)
        if size == 1:
            size = _u(data, pos + 8, 8)
            hdr = 16
        else:
            hdr = 8
            if size == 0:
                size = end - pos
        if size < 8 or pos + size > end:
            break
        box = {'typ': typ, 'start': pos, 'hdr': hdr, 'size': size, 'a': []}
        body_start = pos + hdr
        if typ in _CONTAINER:
            box['a'] = _parse(data, body_start, pos + size)
        elif typ == 'stsd':
            box['a'] = _parse(data, body_start + 8, pos + size)
        elif typ in ('encv', 'hvc1', 'hev1', 'avc1'):
            box['a'] = _parse(data, body_start + 78, pos + size)
        elif typ in ('enca', 'mp4a'):
            box['a'] = _parse(data, body_start + 28, pos + size)
        boxes.append(box)
        pos += size
    return boxes


def _find(boxes, typ):
    for b in boxes:
        if b['typ'] == typ:
            return b
        r = _find(b.get('a', []), typ)
        if r is not None:
            return r
    return None


def _find_all(boxes, typ, out):
    for b in boxes:
        if b['typ'] == typ:
            out.append(b)
        _find_all(b.get('a', []), typ, out)


def _ctr_decrypt(key, iv, data):
    if len(iv) < 16:
        iv = iv + b'\x00' * (16 - len(iv))
    iv16 = iv
    if data:
        # 1) Java javax.crypto（Android 原生 C 加速, 真机首选）
        try:
            from javax.crypto import Cipher as _JC
            from javax.crypto.spec import SecretKeySpec, IvParameterSpec
            _c = _JC.getInstance('AES/CTR/NoPadding')
            _c.init(_JC.DECRYPT_MODE, SecretKeySpec(bytes(key), 'AES'), IvParameterSpec(iv16))
            _gg_ctr_log('java')
            return bytes(_c.doFinal(bytes(data)))
        except Exception:
            pass
        # 2) cryptography C 加速
        if _HAS_CRYPTOGRAPHY:
            try:
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                _gg_ctr_log('cryptography')
                c = Cipher(algorithms.AES(key), modes.CTR(iv16)).decryptor()
                return c.update(data) + c.finalize()
            except Exception:
                pass
    # 3) 纯 Python 回退
    _gg_ctr_log('py')
    return _p_aes_ctr(key, iv16, data)


_gg_ctr_logged = {}


def _gg_ctr_log(mode):
    if mode not in _gg_ctr_logged:
        _gg_ctr_logged[mode] = True
        try:
            _sys.stderr.write('CTR mode %s\n' % mode)
        except Exception:
            pass


def _decrypt_sample(key, iv, sample, subs):
    if not subs:
        return _ctr_decrypt(key, iv, sample)
    if len(iv) < 16:
        iv = iv + b'\x00' * (16 - len(iv))
    out = bytearray(len(sample))
    pos = 0
    enc_parts = []
    for clear_len, enc_len in subs:
        out[pos:pos + clear_len] = sample[pos:pos + clear_len]
        pos += clear_len
        enc_parts.append(sample[pos:pos + enc_len])
        pos += enc_len
    dec = _ctr_decrypt(key, iv, b''.join(enc_parts))
    pos = 0
    dp = 0
    for clear_len, enc_len in subs:
        pos += clear_len
        out[pos:pos + enc_len] = dec[dp:dp + enc_len]
        dp += enc_len
        pos += enc_len
    return bytes(out)


def _sample_offsets(data, stbl):
    stsz = _find(stbl, 'stsz')
    stsc = _find(stbl, 'stsc')
    stco = _find(stbl, 'stco')
    co64 = _find(stbl, 'co64')
    if not stsz or not stsc:
        return []
    is64 = stco is None
    loc = co64 if is64 else stco
    if not loc:
        return []
    p = stsz['start'] + stsz['hdr'] + 4
    sample_size = _u(data, p, 4)
    count = _u(data, p + 4, 4)
    sizes = [sample_size] * count if sample_size else [_u(data, p + 8 + i * 4, 4) for i in range(count)]
    p = stsc['start'] + stsc['hdr'] + 4
    entry = _u(data, p, 4)
    first_chunk = [0] * entry
    samples_per_chunk = [0] * entry
    for i in range(entry):
        q = p + 4 + i * 12
        first_chunk[i] = _u(data, q, 4)
        samples_per_chunk[i] = _u(data, q + 4, 4)
    p = loc['start'] + loc['hdr'] + 4
    chunk_count = _u(data, p, 4)
    offsets = [_u(data, p + 4 + i * (8 if is64 else 4), 8 if is64 else 4) for i in range(chunk_count)]
    spc = []
    for i in range(entry):
        last = first_chunk[i + 1] - 1 if i + 1 < entry else chunk_count
        spc += [samples_per_chunk[i]] * (last - first_chunk[i] + 1)
    out = []
    si = 0
    for ci in range(chunk_count):
        n = spc[ci] if ci < len(spc) else (spc[-1] if spc else 0)
        off = offsets[ci]
        for _ in range(n):
            if si >= count:
                break
            out.append([off, sizes[si]])
            off += sizes[si]
            si += 1
    return out


def _parse_senc(data, senc, iv_len, ivs, subss):
    p = senc['start'] + senc['hdr']
    flags = _u(data, p + 1, 3)
    n = _u(data, p + 4, 4)
    p += 8
    for _ in range(n):
        ivs.append(data[p:p + iv_len])
        p += iv_len
        if flags & 2:
            k = _u(data, p, 2)
            p += 2
            subs = []
            for _ in range(k):
                subs.append((_u(data, p, 2), _u(data, p + 2, 4)))
                p += 6
            subss.append(subs)
        else:
            subss.append([])


def cenc_decrypt(data, key_hex):
    import time as _t
    _t0 = _t.time()
    key = bytes.fromhex(key_hex)
    if len(key) != 16:
        raise ValueError('content key must 16B')
    buf = bytearray(data)
    boxes = _parse(buf, 0, len(buf))
    moov = _find(boxes, 'moov')
    if moov is None:
        raise ValueError('no moov')
    traks = []
    _find_all(moov.get('a', []), 'trak', traks)
    for trak in traks:
        stbl = _find(trak.get('a', []), 'stbl')
        senc = _find(trak.get('a', []), 'senc')
        if stbl is None or senc is None:
            continue
        tenc = _find(trak.get('a', []), 'tenc')
        iv_len = (buf[tenc['start'] + tenc['hdr'] + 7] & 0xFF) if tenc else 8
        frma = _find(trak.get('a', []), 'frma')
        orig = bytes(buf[frma['start'] + frma['hdr']:frma['start'] + frma['hdr'] + 4]) if frma else None
        offsets = _sample_offsets(buf, stbl.get('a', []))
        ivs, subss = [], []
        _parse_senc(buf, senc, iv_len, ivs, subss)
        n = min(len(offsets), len(ivs), len(subss))
        _sz = 0
        for i in range(n):
            off, sz = offsets[i]
            sample = bytes(buf[off:off + sz])
            buf[off:off + sz] = _decrypt_sample(key, ivs[i], sample, subss[i])
            _sz += sz
        _sys.stderr.write('GUOGUO dec trak %d n=%d sz=%d %.2fs\n' % (traks.index(trak), n, _sz, _t.time() - _t0))
        if orig:
            for t in ('encv', 'enca'):
                b = _find(trak.get('a', []), t)
                if b:
                    buf[b['start'] + 4:b['start'] + 8] = orig
        for t in ('sinf', 'senc', 'saio', 'saiz'):
            b = _find(trak.get('a', []), t)
            if b:
                buf[b['start'] + 4:b['start'] + 8] = b'free'
    return bytes(buf)


# ---------------- 净化 hvcC/avcC（去除字节私有尾部，兼容 IJK/硬解） ----------------
def _hvcC_clean_payload(payload):
    """重建 hvcC payload：只保留标准 VPS/SPS/PPS array（NAL 32/33/34），丢弃 ByteVC 私有 NAL。"""
    try:
        if len(payload) < 23:
            return None
        num_arrays = payload[22] & 0xFF
        head = bytearray(payload[:23])
        p = 23
        kept = bytearray()
        kept_count = 0
        for _ in range(num_arrays):
            if p + 3 > len(payload):
                return None
            typ = payload[p]
            p += 1
            n = _u(payload, p, 2)
            p += 2
            arr = bytearray()
            ok = True
            for _ in range(n):
                if p + 2 > len(payload):
                    ok = False
                    break
                ln = _u(payload, p, 2)
                p += 2
                if p + ln > len(payload):
                    ok = False
                    break
                arr += struct.pack('>H', ln) + payload[p:p + ln]
                p += ln
            if not ok:
                return None
            if (typ & 0x3F) in (32, 33, 34):
                kept += bytes([typ]) + struct.pack('>H', n) + arr
                kept_count += 1
        head[22] = kept_count
        return bytes(head) + bytes(kept)
    except Exception:
        return None


def _clean_csd(data):
    """净化 stsd 里的 hvcC（重建去掉私有 NAL）/ avcC（截断私有尾部），并修正 stco/co64 偏移。"""
    buf = bytearray(data)
    total_del = 0
    min_clean = -1
    try:
        # hvcC: 重建
        pos = 0
        while True:
            i = buf.find(b'hvcC', pos)
            if i < 0:
                break
            pos = i + 4
            box_start = i - 4
            try:
                size32 = _u(buf, box_start, 4)
            except Exception:
                break
            hdr = 8
            if size32 == 1:
                try:
                    box_size = _u(buf, box_start + 8, 8)
                except Exception:
                    break
                hdr = 16
            else:
                box_size = size32
            payload = bytes(buf[box_start + hdr:box_start + box_size])
            new_payload = _hvcC_clean_payload(payload)
            if new_payload and len(new_payload) < len(payload):
                new_size = hdr + len(new_payload)
                if new_size >= 16:
                    if hdr == 8:
                        buf[box_start:box_start + 4] = struct.pack('>I', new_size)
                    else:
                        buf[box_start + 8:box_start + 16] = struct.pack('>Q', new_size)
                    del buf[box_start + hdr + len(new_payload):box_start + box_size]
                    buf[box_start + hdr:box_start + hdr + len(new_payload)] = new_payload
                    total_del += box_size - new_size
                    if min_clean < 0:
                        min_clean = box_start
        # avcC: 截断
        pos = 0
        while True:
            i = buf.find(b'avcC', pos)
            if i < 0:
                break
            pos = i + 4
            box_start = i - 4
            try:
                size32 = _u(buf, box_start, 4)
            except Exception:
                break
            hdr = 8
            if size32 == 1:
                try:
                    box_size = _u(buf, box_start + 8, 8)
                except Exception:
                    break
                hdr = 16
            else:
                box_size = size32
            std_len = _avcC_std_len(bytes(buf[box_start + hdr:box_start + box_size]))
            if std_len and std_len < box_size - hdr:
                new_size = hdr + std_len
                if new_size >= 16:
                    if hdr == 8:
                        buf[box_start:box_start + 4] = struct.pack('>I', new_size)
                    else:
                        buf[box_start + 8:box_start + 16] = struct.pack('>Q', new_size)
                    del buf[box_start + hdr + std_len:box_start + box_size]
                    total_del += box_size - new_size
                    if min_clean < 0:
                        min_clean = box_start
        # 修正 chunk 偏移（仅当 moov/净化点在 mdat 之前时，mdat 随之前移）
        mdat_i = buf.find(b'mdat')
        if total_del and mdat_i > 0 and (min_clean < 0 or mdat_i > min_clean):
            for tag in (b'stco', b'co64'):
                pos = 0
                while True:
                    i = buf.find(tag, pos)
                    if i < 0:
                        break
                    pos = i + 4
                    b_start = i - 4
                    try:
                        b_size = _u(buf, b_start, 4)
                    except Exception:
                        break
                    if b_size < 16 or b_start + b_size > len(buf):
                        continue
                    n = _u(buf, b_start + 8, 4)
                    if tag == b'stco':
                        for k in range(n):
                            off = _u(buf, b_start + 12 + k * 4, 4)
                            if off >= total_del:
                                buf[b_start + 12 + k * 4:b_start + 16 + k * 4] = struct.pack('>I', off - total_del)
                    else:
                        for k in range(n):
                            off = _u(buf, b_start + 12 + k * 8, 8)
                            if off >= total_del:
                                buf[b_start + 12 + k * 8:b_start + 20 + k * 8] = struct.pack('>Q', off - total_del)
        # 同时把 stsd 里 bv1C/bv2C/ByteVC 相关私有 box 整体转 free（保险）
        pos = 0
        while True:
            i = buf.find(b'ByteVC', pos)
            if i < 0:
                break
            pos = i + 6
            # 找到包含它的 box 头（向前搜最近的 4 字节 size + 4 字节 type）
            for back in range(4, 256, 4):
                s0 = i - back
                if s0 >= 0:
                    try:
                        bsz = _u(buf, s0, 4)
                    except Exception:
                        continue
                    if bsz >= 8 and s0 + bsz <= len(buf):
                        buf[s0 + 4:s0 + 8] = b'free'
                        break
    except Exception:
        pass
    return bytes(buf)


def _hvcC_std_len(payload):
    """解析 hvcC payload，返回标准长度（不含私有尾部），异常返回 0。"""
    try:
        if len(payload) < 23:
            return 0
        num_arrays = payload[22] & 0xFF
        p = 23
        for _ in range(num_arrays):
            if p + 3 > len(payload):
                return 0
            p += 1
            num_nalus = _u(payload, p, 2)
            p += 2
            for _ in range(num_nalus):
                if p + 2 > len(payload):
                    return 0
                n = _u(payload, p, 2)
                p += 2
                if p + n > len(payload):
                    return 0
                p += n
        return p
    except Exception:
        return 0


def _avcC_std_len(payload):
    """解析 avcC payload 标准长度。avcC 结构：6 字节头 + numOfSPS(1) + sps + numOfPPS(1) + pps + ext。"""
    try:
        if len(payload) < 7:
            return 0
        p = 6
        n_sps = payload[p] & 0xFF
        p += 1
        for _ in range(n_sps):
            if p + 2 > len(payload):
                return 0
            n = _u(payload, p, 2)
            p += 2
            if p + n > len(payload):
                return 0
            p += n
        if p >= len(payload):
            return p
        n_pps = payload[p] & 0xFF
        p += 1
        for _ in range(n_pps):
            if p + 2 > len(payload):
                return 0
            n = _u(payload, p, 2)
            p += 2
            if p + n > len(payload):
                return 0
            p += n
        # 高版本 avcC 有额外扩展（chroma/bitdepth 等），保守保留
        if p + 4 <= len(payload) and payload[p] == 0xFD:
            p += 4
        return p
    except Exception:
        return 0


# ---------------- Spider ----------------
class Spider(Spider):
    def getName(self):
        return "果果短剧"

    def init(self, extend=""):
        global SIGN_HOST
        try:
            j = json.loads((extend or '').strip() or '{}')
            host = str(j.get('signHost') or '').strip()
            if host:
                SIGN_HOST = host.rstrip('/')
        except Exception:
            pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ---------- 首页 ----------
    def homeContent(self, filter):
        return {'class': [{'type_id': cid, 'type_name': name} for cid, name in CATES],
                'filters': {}}

    def homeVideoContent(self):
        return self.categoryContent('short_play', 1, False, {})

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 18, 'total': 999999}
        try:
            j = _landpage(tid, (int(pg) - 1) * 18)
            videos = []
            for v in _extract_videos(j):
                videos.append({
                    'vod_id': '%s|%s' % (v.get('series_id', ''), v.get('vid') or v.get('video_id', '')),
                    'vod_name': v.get('title', ''),
                    'vod_pic': v.get('cover') or v.get('thumb') or '',
                    'vod_remarks': v.get('episode_total') or v.get('episode_count') or '',
                    'vod_content': v.get('abstract') or v.get('description') or ''
                })
            result['list'] = videos
        except Exception:
            pass
        return result

    # ---------- 详情 ----------
    def detailContent(self, ids):
        rid = ids[0] if isinstance(ids, (list, tuple)) else ids
        try:
            parts = str(rid).split('|')
            series_id = parts[0]
            vid = parts[1] if len(parts) > 1 else parts[0]
            eps = _episode_vids(series_id, vid)
            play_url = '#'.join(['第%d集$%s' % (i + 1, v) for i, v in enumerate(eps)])
            vod = {
                'vod_id': rid,
                'vod_name': series_id,
                'vod_pic': '',
                'vod_content': '共 %d 集' % len(eps),
                'vod_remarks': '%d 集' % len(eps),
                'vod_actor': '果果短剧',
                'vod_play_from': '果果',
                'vod_play_url': play_url
            }
            return {'list': [vod]}
        except Exception as e:
            return {'list': [{
                'vod_id': rid, 'vod_name': '加载失败', 'vod_content': '加载失败: %s' % e,
                'vod_remarks': '加载失败', 'vod_actor': '', 'vod_play_from': '果果',
                'vod_play_url': '', 'vod_pic': ''
            }]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        vid = str(id).strip()
        try:
            vm = _video_model(vid)
            if not vm:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            vl = vm.get('video_list') or []
            if not vl:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            # 选最高清晰度
            item = None
            h_map = {}
            for it in vl:
                meta = it.get('video_meta') or {}
                h = meta.get('vheight') or meta.get('vwidth') or 0
                h_map.setdefault(int(h), it)
            item = h_map[max(h_map)] if h_map else vl[0]
            main_url = _decode_main_url(item.get('main_url'))
            enc = item.get('encrypt_info') or {}
            if not main_url:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
            if enc.get('encrypt'):
                spade_a = enc.get('spade_a') or ''
                key = _derive_key(spade_a)
                if not key:
                    return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}
                # 本地代理解密: 走 OK影视 内置 proxy(9978) 标准 py 通道, 由壳调 localProxy 完成 下载+解密
                # url/key 用 urlsafe base64(去填充), 避免 + / = 破坏 query 解析
                import base64 as _b64
                u = _b64.urlsafe_b64encode(main_url.encode()).decode().rstrip('=')
                k = _b64.urlsafe_b64encode(key.encode()).decode().rstrip('=')
                q = urllib.parse.urlencode({
                    'do': 'py', 'type': '果果短剧',
                    'url': u, 'key': k})
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': 'http://127.0.0.1:9978/proxy?%s' % q,
                        'header': {}, 'pic': '', 'name': ''}
            else:
                # 未加密直接播
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': main_url,
                        'header': {'User-Agent': UA, 'Referer': 'https://www.douyin.com/'},
                        'pic': '', 'name': ''}
        except Exception:
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': {}, 'pic': '', 'name': ''}

    # ---------- 本地代理: 下载 + CENC 解密 ----------
    def localProxy(self, param):
        import sys as _sys
        def _q(v):
            return v[0] if isinstance(v, (list, tuple)) and v else v

        def _b64d(s):
            s = s.strip()
            try:
                return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4)).decode()
            except Exception:
                return base64.b64decode(s + '=' * (-len(s) % 4)).decode()
        try:
            u = _q(param.get('url', '')) or ''
            if u.startswith('http'):
                main_url = u
            else:
                main_url = _b64d(u)
            k = _q(param.get('key', '')) or ''
            key = _b64d(k)
            if not main_url or not key:
                return [200, 'video/mp4', {'Content-Type': 'video/mp4'}, b'']
            ck = main_url + '|' + key
            # 同源缓存, 避免播放器并发 Range 请求重复全量下载
            if _SRV_CACHE['k'] == ck and _SRV_CACHE['body'] is not None:
                body = _SRV_CACHE['body']
                print('GGP cache hit', len(body), file=_sys.stderr)
            else:
                t0 = time.time()
                try:
                    # Java 网络栈优先: 字节 CDN 对 Python TLS 指纹黑洞, Java(OK影视进程内) 正常
                    data = _java_dl(main_url, None, 60)
                    print('GGP java dl', len(data), '%.1fs' % (time.time() - t0), file=_sys.stderr)
                except Exception as e:
                    print('GGP java dl fail', type(e).__name__, str(e)[:60], file=_sys.stderr)
                    t0 = time.time()
                    data = _dl_mp4(main_url)
                    print('GGP py dl', len(data), '%.1fs' % (time.time() - t0), file=_sys.stderr)
                t0 = time.time()
                body = cenc_decrypt(data, key)
                body = _clean_csd(body)  # 去除 hvcC/avcC 私有尾部，保证 IJK/硬解可解析
                print('GGP dec', len(body), '%.1fs' % (time.time() - t0),
                      'ByteVC', b'ByteVC' in body, file=_sys.stderr)
                _SRV_CACHE['k'] = ck
                _SRV_CACHE['body'] = body
            # OK影视 py 引擎要求四元组, headers 必须是 dict(Java asMap), 不能 list-of-list
            return [200, 'video/mp4', {'Content-Type': 'video/mp4'}, body]
        except Exception as e:
            print('GGP ERR', type(e).__name__, str(e)[:80], file=_sys.stderr)
            return [200, 'video/mp4', {'Content-Type': 'video/mp4'}, b'']

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg=1):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 20, 'total': 999999}
        try:
            videos = []
            for v in _search(key):
                videos.append({
                    'vod_id': '%s|%s' % (v.get('series_id', ''), v.get('vid') or v.get('video_id', '')),
                    'vod_name': v.get('title', ''),
                    'vod_pic': v.get('cover') or v.get('thumb') or '',
                    'vod_remarks': v.get('episode_total') or ''
                })
            result['list'] = videos
        except Exception:
            pass
        return result

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)
