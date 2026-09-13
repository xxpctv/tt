# -*- coding: utf-8 -*-
# 蜻蜓广播 - 独立可用版
# 来源: aidaox-20260829.jar csp_QingtingFM（已解密去混淆）
# 兼容: OK影视 / 影视仓（TVBox Python 引擎）
# 接口: https://webbff.qtfm.cn/www (GraphQL) / https://webapi.qtfm.cn/api/pc/radio/{id}
# 播放: https://lhttp-hw.qtfm.cn/live/{id}/64k.mp3

from base.spider import Spider
import requests
import json


class Spider(Spider):
    def getName(self):
        return "蜻蜓广播"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
            'Referer': 'https://www.qtfm.cn',
            'Content-Type': 'application/json; charset=utf-8'
        }

    def _post(self, query):
        body = json.dumps({'query': query}, ensure_ascii=False)
        r = requests.post('https://webbff.qtfm.cn/www', data=body.encode('utf-8'), headers=self._headers(), timeout=12)
        return r.json()

    def _get(self, url):
        h = dict(self._headers())
        h.pop('Content-Type', None)
        r = requests.get(url, headers=h, timeout=12)
        return r.json()

    # ---------- 首页 ----------
    def homeContent(self, filter):
        cates = [
            ('217', '广东'), ('99', '浙江'), ('3', '北京'), ('5', '天津'), ('7', '河北'),
            ('83', '上海'), ('19', '山西'), ('31', '内蒙古'), ('44', '辽宁'), ('59', '吉林'),
            ('69', '黑龙江'), ('85', '江苏'), ('111', '安徽'), ('129', '福建'), ('139', '江西'),
            ('151', '山东'), ('169', '河南'), ('187', '湖北'), ('202', '湖南'), ('239', '广西'),
            ('254', '海南'), ('257', '重庆'), ('259', '四川'), ('281', '贵州'), ('291', '云南'),
            ('316', '陕西'), ('327', '甘肃'), ('351', '宁夏'), ('357', '新疆'), ('308', '西藏'),
            ('342', '青海'), ('433', '资讯'), ('442', '音乐'), ('429', '交通'), ('439', '经济'),
            ('432', '文艺'), ('441', '都市'), ('430', '体育'), ('431', '双语'), ('440', '综合'),
            ('438', '生活'), ('435', '旅游'), ('436', '曲艺'), ('434', '方言'),
        ]
        return {
            'class': [{'type_id': cid, 'type_name': name} for cid, name in cates],
            'filters': {}
        }

    def homeVideoContent(self):
        return self.categoryContent('217', 1, False, {})

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg, filter, extend):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 12, 'total': 999999}
        try:
            q = '{\n    radioPage(cid: %s, page: %s){\n      contents\n    }\n  }' % (tid, pg)
            j = self._post(q)
            items = j['data']['radioPage']['contents']['items']
            videos = []
            for it in items:
                pic = it.get('imgUrl') or ''
                if pic and not pic.startswith('https'):
                    pic = 'https:' + pic
                videos.append({
                    'vod_id': it.get('id', ''),
                    'vod_name': it.get('title', ''),
                    'vod_pic': pic,
                    'vod_remarks': it.get('desc', '')
                })
            result['list'] = videos
        except Exception:
            pass
        return result

    # ---------- 详情 ----------
    def detailContent(self, ids):
        rid = ids[0] if isinstance(ids, (list, tuple)) else ids
        try:
            j = self._get('https://webapi.qtfm.cn/api/pc/radio/%s' % rid)
            album = j.get('album', {})
            title = album.get('title', '')
            vid = album.get('id', rid)
            vod = {
                'vod_id': rid,
                'vod_name': title,
                'vod_pic': album.get('cover', ''),
                'vod_content': album.get('description', ''),
                'vod_remarks': '蜻蜓FM',
                'vod_actor': title,
                'vod_play_from': '蜻蜓FM',
                'vod_play_url': '%s$%s' % (title, vid)
            }
            return {'list': [vod]}
        except Exception as e:
            return {'list': [{
                'vod_id': rid, 'vod_name': '加载失败', 'vod_content': '加载失败: %s' % e,
                'vod_remarks': '加载失败', 'vod_actor': '', 'vod_play_from': '蜻蜓FM',
                'vod_play_url': '', 'vod_pic': ''
            }]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        url = 'https://lhttp-hw.qtfm.cn/live/%s/64k.mp3' % id
        return {
            'parse': 0, 'jx': 0, 'playUrl': '', 'url': url,
            'header': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                       'Referer': 'https://www.qtfm.cn'},
            'pic': '', 'name': ''
        }

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg=1):
        result = {'list': [], 'page': pg, 'pagecount': 9999, 'limit': 12, 'total': 999999}
        try:
            q = '{\n        searchResultsPage(keyword:"%s", page:%s, include:"channel_live" ) {\n          tdk,\n          searchData,\n          numFound\n        }\n      }' % (key, pg)
            j = self._post(q)
            items = j['data']['searchResultsPage']['searchData']
            videos = []
            for it in items:
                videos.append({
                    'vod_id': it.get('id', ''),
                    'vod_name': it.get('title', ''),
                    'vod_pic': it.get('cover', ''),
                    'vod_remarks': it.get('description', '')
                })
            result['list'] = videos
        except Exception:
            pass
        return result

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    def localProxy(self, param):
        return {}
