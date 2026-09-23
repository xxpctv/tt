# -*- coding: utf-8 -*-
"""
Ajeo-KafLive 咖啡体育（原 csp_KafLiveAmns）独立版
协议依据 aidaox/feimao jar 原版 com.github.catvod.spider.KafLiveAmns 全链路复现（已 100% 解明并实测 200）：
  - 域名：https://www.kafeizhibo.cc（OK 配置 ext 以 http 开头可覆盖）
  - 分类：静态 all=全部 / hot=热门 / 1=足球 / 2=篮球
  - 列表：GET /api/v1/schedule?size=30&page=<pg>&type=<tid>&platform=h5  -> data[]
  - 详情：GET /api/v1/room/<roomId>  -> data（room_info 或 data）-> signals[] 线路 + archor.stream_url 兜底
  - 播放：playerContent 直回 stream_url + header（UA/Referer/Accept），无壳代理、无签名、无 native
  - 直播：liveContent 拉 /api/v1/archor?platform=h5 构造 M3U8
兼容：OK影视 / 影视仓（TVBox Python 引擎）
"""
import json
import ssl
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider:
        pass

_BASE = 'https://www.kafeizhibo.cc'
_UA = ('Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 '
       'Chrome/120.0.0.0 Mobile Safari/537.36')

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA, 'Accept': 'application/json', 'Referer': _BASE + '/'})
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=timeout) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''


def _fetch_json(url):
    """GET + code==200 校验，失败返回 None（对齐原版 fetchJson）"""
    t = _get(url)
    if not t:
        return None
    try:
        j = json.loads(t)
    except Exception:
        return None
    if j.get('code') != 200:
        return None
    return j


def _join(base, path):
    """原版 a()：base 去尾斜杠 + path 补前斜杠拼接"""
    b = base.rstrip('/') if base.endswith('/') else base
    if not path.startswith('/'):
        path = '/' + path
    return b + path


def _status_remark(hs, as_, status):
    """原版 c(home_score, away_score, status)：状态备注"""
    st = (status or '').lower()
    if st == 'live':
        return '%s-%s 直播中' % (hs, as_)
    if st in ('finished', 'end'):
        return '%s-%s 已结束' % (hs, as_)
    if st == 'not_started':
        return '未开赛'
    return status if status else '赛程'


def _vod_id(obj):
    """原版 b(JSONObject)：archor.room_id -> archors[0].room_id -> id/room_id"""
    try:
        a = obj.get('archor')
        if isinstance(a, dict):
            rid = str(a.get('room_id') or '')
            if rid:
                return rid
        arr = obj.get('archors')
        if isinstance(arr, list) and arr:
            rid = str(arr[0].get('room_id') or '')
            if rid:
                return rid
        return str(obj.get('room_id') or obj.get('id') or '')
    except Exception:
        return str(obj.get('id') or '')


def _base_url(ext):
    ext = (ext or '').strip()
    if ext.startswith('http'):
        return ext.rstrip('/')
    return _BASE


class Spider(_BaseSpider):
    name = '咖啡体育'
    siteKey = 'KafLive'

    def init(self, extend=''):
        self.base = _base_url(extend)
        return ''

    def _base(self):
        return getattr(self, 'base', None) or _BASE

    def homeContent(self, filter):
        classes = [
            {'type_id': 'all', 'type_name': '全部'},
            {'type_id': 'hot', 'type_name': '热门'},
            {'type_id': '1', 'type_name': '足球'},
            {'type_id': '2', 'type_name': '篮球'},
        ]
        return {'class': classes, 'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg_i = max(1, int(pg or 1))
        except Exception:
            pg_i = 1
        if not tid:
            tid = 'all'
        url = _join(self._base(), '/api/v1/schedule?size=30&page=%d&type=%s&platform=h5' % (pg_i, tid))
        j = _fetch_json(url)
        if not j:
            return {'list': [], 'page': {'page': pg_i, 'pagecount': 1, 'limit': 30, 'total': 0}}
        arr = j.get('data') or []
        out = []
        for it in arr:
            if not isinstance(it, dict):
                continue
            home = it.get('home_team') or ''
            away = it.get('away_team') or ''
            league = it.get('league_name') or ''
            hs = it.get('home_score') or 0
            as_ = it.get('away_score') or 0
            status = it.get('status') or ''
            pic = it.get('home_team_logo') or ''
            if not pic:
                hm = it.get('homeTeam')
                if isinstance(hm, dict):
                    pic = hm.get('logo') or ''
            out.append({
                'vod_id': _vod_id(it),
                'vod_name': '%s vs %s' % (home, away),
                'vod_pic': pic,
                'vod_remarks': '%s %s' % (league, _status_remark(hs, as_, status)),
            })
        n = len(out)
        return {
            'list': out,
            'page': {'page': pg_i, 'pagecount': max(1, (n + 29) // 30), 'limit': 30, 'total': n},
        }

    def detailContent(self, ids):
        if not ids:
            return {'list': []}
        rid = str(ids[0])
        url = _join(self._base(), '/api/v1/room/' + rid)
        j = _fetch_json(url)
        if not j:
            return {'list': []}
        data = j.get('data')
        if not isinstance(data, dict):
            return {'list': [], 'msg': '房间不存在'}
        info = data.get('room_info')
        if not isinstance(info, dict):
            info = data
        name = info.get('title') or ''
        if not name:
            name = '%s vs %s' % (info.get('home_team') or '', info.get('away_team') or '')
        lines = []
        urls = []
        signals = data.get('signals')
        if isinstance(signals, list):
            for i, s in enumerate(signals or []):
                if not isinstance(s, dict):
                    continue
                su = s.get('stream_url') or ''
                if not su:
                    continue
                sn = s.get('name') or '线路%d' % (i + 1)
                lines.append(sn)
                urls.append('%s$%s' % (sn, su))
        archor = data.get('archor')
        if isinstance(archor, dict) and (archor.get('stream_url') or ''):
            lines.append('咖啡Live')
            urls.append('直播$' + archor['stream_url'])
        if not lines:
            return {'list': [], 'msg': '暂无可用直播流'}
        league = info.get('league') or '咖啡体育'
        notice = info.get('notice_h5') or info.get('notice') or ''
        content = '此接口免费，请勿相信视频中任何广告。\n' + notice
        vod = {
            'vod_id': rid,
            'vod_name': name,
            'vod_pic': '',
            'vod_remarks': league,
            'vod_content': content,
            'vod_play_from': '$$$'.join(lines),
            'vod_play_url': '#'.join(urls),
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {'url': '', 'msg': '播放地址为空'}
        return {
            'url': id,
            'header': {
                'User-Agent': _UA,
                'Referer': self._base() + '/',
                'Accept': 'application/json',
            },
        }

    def liveContent(self, ids):
        """拉主播列表构造 M3U8（对齐原版 liveContent）"""
        url = _join(self._base(), '/api/v1/archor?platform=h5')
        j = _fetch_json(url)
        if not j:
            return ''
        arr = j.get('data') or []
        if not arr:
            return ''
        out = ['#EXTM3U']
        for it in arr:
            if not isinstance(it, dict):
                continue
            su = it.get('stream_url') or ''
            if not su:
                continue
            title = it.get('title') or ''
            if not title:
                title = it.get('name') or '直播'
            league = it.get('league_name') or '体育'
            mi = it.get('match_info')
            logo = ''
            if isinstance(mi, dict):
                logo = mi.get('home_team_logo') or ''
            rid = it.get('room_id') or it.get('archor_id') or ''
            title_c = title.replace('"', "'")
            out.append('#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s",%s' %
                       (rid, title_c, logo, league, title_c))
            out.append(su)
        return '\n'.join(out) + '\n'

    def searchContent(self, key, quick=True, pg=1):
        # 原版无搜索
        return {}


class KafLiveAmns(Spider):
    """OK影视 api=csp_KafLiveAmns 别名类"""
    pass


def main():
    s = Spider()
    h = s.homeContent(False)
    print('首页分类:', [c['type_name'] for c in h['class']])
    c = s.categoryContent('hot', 1, None, None)
    print('hot 列表条数:', len(c['list']))
    if c['list']:
        print('首项:', c['list'][0])
        d = s.detailContent([c['list'][0]['vod_id']])
        if d['list']:
            vod = d['list'][0]
            print('详情:', vod['vod_name'], '|', vod['vod_remarks'], '| 线路:', vod['vod_play_from'])
            ep0 = vod['vod_play_url'].split('#')[0]
            pid = ep0.split('$')[1]
            p = s.playerContent('', pid, [])
            print('播放:', p['url'][:100], '| header keys:', list(p['header'].keys()))


if __name__ == '__main__':
    main()
