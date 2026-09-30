# -*- coding: utf-8 -*-
# by @嗷呜
import concurrent.futures
import json
import re
import sys
import time
from base64 import b64decode, b64encode
import requests
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.host = "https://vip.wwgz.cn:5200"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Referer': self.host + '/',
            'Accept': 'text/html'
        }
        self.cateConfig = {
            "12": [{"key": "cateId", "name": "类型", "value": [{"n": "国产剧", "v": "12"}]}],
            "4": [{"key": "cateId", "name": "类型", "value": [{"n": "动漫", "v": "4"}]}],
            "1": [{"key": "cateId", "name": "类型", "value": [{"n": "电影", "v": "1"}]}],
            "2": [{"key": "cateId", "name": "类型", "value": [{"n": "电视剧", "v": "2"}]}],
            "3": [{"key": "cateId", "name": "类型", "value": [{"n": "综艺", "v": "3"}]}],
            "26": [{"key": "cateId", "name": "类型", "value": [{"n": "短剧", "v": "26"}]}]
        }
        self.filterConfig = {}

    def getName(self):
        return "农民影视"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def homeContent(self, filter):
        result = {}
        classes = [
            {'type_name': '国产剧', 'type_id': '12'},
            {'type_name': '动漫', 'type_id': '4'},
            {'type_name': '电影', 'type_id': '1'},
            {'type_name': '电视剧', 'type_id': '2'},
            {'type_name': '综艺', 'type_id': '3'},
            {'type_name': '短剧', 'type_id': '26'}
        ]
        try:
            data = self.fetch(self.host, headers=self.headers).text
            doc = pq(data)
            videos = []
            seen_ids = set()
            for item in doc('.globalPicList li:has(img)').items():
                vod_id = self.host + (item('a').attr('href') or '')
                if vod_id not in seen_ids:
                    seen_ids.add(vod_id)
                    pic_url = item('img').attr('data-echo') or item('img').attr('data-src') or item('img').attr('src') or ''
                    if pic_url and 'pic.lzzypic.com' in pic_url:
                        pic_url = pic_url.replace('https://pic.lzzypic.com', 'https://img.lzzyimg.com')
                    videos.append({
                        'vod_id': vod_id,
                        'vod_name': item('.sTit').text() or '',
                        'vod_pic': pic_url,
                        'vod_remarks': item('.sBottom').text() or ''
                    })
            result['class'] = classes
            result['filters'] = self.cateConfig
            result['list'] = videos
        except Exception as e:
            print(f"首页数据获取失败: {str(e)}")
            result['class'] = classes
            result['filters'] = self.cateConfig
            result['list'] = []
        return result

    def homeVideoContent(self):
        pass

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        try:
            if tid == "4-dm":
                url = "https://www.wwgz.cn/vod-list-id-4-pg-{}-order--by-hits-class-0-year-0-letter--area-大陆-lang-.html".format(pg)
            else:
                cateId = tid
                url = f"{self.host}/vod-list-id-{cateId}-pg-{pg}.html"

            data = self.fetch(url, headers=self.headers).text
            doc = pq(data)

            videos = []
            for item in doc('.globalPicList li').items():
                pic_url = item('img').attr('data-echo') or item('img').attr('data-src') or item('img').attr('src') or ''
                if pic_url and 'pic.lzzypic.com' in pic_url:
                    pic_url = pic_url.replace('https://pic.lzzypic.com', 'https://img.lzzyimg.com')
                videos.append({
                    'vod_id': self.host + (item('a').attr('href') or ''),
                    'vod_name': item('.sTit').text() or '',
                    'vod_pic': pic_url,
                    'vod_remarks': item('.sBottom').text() or ''
                })

            result['list'] = videos
            result['page'] = pg
            result['pagecount'] = 9999
            result['limit'] = 90
            result['total'] = 999999
        except Exception as e:
            print(f"分类数据获取失败: {str(e)}")
            result['list'] = []
            result['page'] = pg
            result['pagecount'] = 1
            result['limit'] = 90
            result['total'] = 0
        return result

    def detailContent(self, ids):
        result = {}
        try:
            url = ids[0]
            data = self.fetch(url, headers=self.headers).text
            doc = pq(data)

            play_from = []
            play_url = []

            tab_box = doc('#leftTabBox')
            if tab_box:
                # 先收集线路名（.hd li 可能含非播放线路 tab，故仅作候选名，按索引与 .numList 对齐）
                tab_names = []
                for tab in tab_box('.hd li').items():
                    t = (tab.text() or '').strip()
                    if t:
                        tab_names.append(t)

                # 线路名与集串必须严格同步：遍历 .numList，仅在该线路有有效集时同时追加，
                # 保证 vod_play_from 与 vod_play_url 的 $$$ 组数一一对应，
                # 否则壳按线路索引取播放组会拿到 null 并对其 trim 导致崩溃。
                for idx, nl in enumerate(tab_box('.numList').items()):
                    eps = []
                    for ep in nl('li a').items():
                        en = (ep.text() or '').strip()
                        eu = ep.attr('href')
                        if en and eu:
                            # 清洗集名中的分隔符，避免壳按 $/# 拆分错位
                            en = en.replace('$', '').replace('#', '').strip() or ('第%d集' % (len(eps) + 1))
                            eps.append(en + '$' + self.host + eu)
                    if not eps:
                        continue
                    line_name = tab_names[idx] if idx < len(tab_names) else ('线路%d' % (len(play_from) + 1))
                    play_from.append(line_name)
                    play_url.append('#'.join(eps))

            name = doc('h1.title').text()
            if not name:
                name = doc('h1').text()
            pic = doc('.page-hd img').attr('src') or ''

            vod = {
                'vod_id': ids[0],
                'vod_name': str(name) if name else '',
                'vod_pic': str(pic) if pic else '',
                'vod_year': '',
                'vod_area': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_content': '',
                'vod_remarks': '',
            }
            # 有有效线路才返回播放字段（组数严格一致）；无线路不带 play_from/play_url，避免壳 trim null
            if play_from and len(play_from) == len(play_url):
                vod['vod_play_from'] = '$$$'.join(play_from)
                vod['vod_play_url'] = '$$$'.join(play_url)
            result['list'] = [vod]
        except Exception as e:
            print(f"详情数据获取失败: {str(e)}")
            result['list'] = [{'vod_id': ids[0] if ids else '', 'vod_name': '', 'vod_pic': '', 'vod_year': '', 'vod_area': '', 'vod_actor': '', 'vod_director': '', 'vod_content': '', 'vod_remarks': ''}]
        return result

    def searchContent(self, key, quick, pg="1"):
        result = {}
        try:
            url = f"{self.host}/index.php?m=vod-search"
            data = {'wd': key}
            headers = {
                'User-Agent': self.headers['User-Agent'],
                'Referer': self.host + '/'
            }
            html = self.post(url, data=data, headers=headers).text
            doc = pq(html)

            videos = []
            for item in doc('#data_list li').items():
                pic_url = item('.lazyload').attr('data-src') or ''
                if pic_url and 'pic.lzzypic.com' in pic_url:
                    pic_url = pic_url.replace('https://pic.lzzypic.com', 'https://img.lzzyimg.com')
                videos.append({
                    'vod_id': self.host + (item('a').attr('href') or ''),
                    'vod_name': item('.sTit').text() or '',
                    'vod_pic': pic_url,
                    'vod_remarks': item('.sDes').eq(-1).text() or ''
                })

            result['list'] = videos
            result['page'] = pg
        except Exception as e:
            print(f"搜索数据获取失败: {str(e)}")
            result['list'] = []
            result['page'] = pg
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        try:
            if '@' in id:
                ids = id.split('@')
                if not ids[0]:
                    raise Exception('未找到播放地址')

                js_url = f"{self.host}/player/{ids[0]}.js"
                js_data = self.fetch(js_url, headers=self.headers).text
                jxurl = re.search(r'http.*?url=', js_data).group()

                data = self.fetch(f"{jxurl}{ids[1]}", headers=self.headers).text
                matches = re.findall(r'http.*?url=', data)

                if matches:
                    url = []
                    for i, x in enumerate(matches):
                        js = {'jx': x, 'id': ids[1]}
                        purl = f"{self.getProxyUrl()}&wdict={self.e64(json.dumps(js))}"
                        url.extend([f'线路{i + 1}', purl])
                else:
                    url = re.search(r"url='(.*?)'", data).group(1)

                if not url:
                    raise Exception('未找到播放地址')

                p = 0
            else:
                # 普通剧集：id 为播放页地址(vod-play-id-x-src-N-num-M.html)，
                # 播放页变量 mac_url 内含各线路各集真实 m3u8。脚本内直接取出当前集直链，
                # 以 parse=0 直连返回，避免壳走嗅探分支时先以空 url 刷新界面导致崩溃。
                p = 0
                url = (id or '').strip()
                seg = re.search(r'src-(\d+)-num-(\d+)', url)
                if seg:
                    src_idx, num = int(seg.group(1)) - 1, int(seg.group(2))
                    html = self.fetch(url, headers=self.headers).text
                    mac = re.search(r"mac_url\s*=\s*['\"]([^'\"]+)['\"]", html)
                    if mac:
                        lines = mac.group(1).split('$$$')
                        line = lines[src_idx] if 0 <= src_idx < len(lines) else lines[0]
                        picks = []
                        for item in line.split('#'):
                            if '$' in item:
                                ep_name, ep_url = item.split('$', 1)
                                picks.append((ep_name.strip(), ep_url.strip()))
                        direct = None
                        for ep_name, ep_url in picks:
                            nums = re.sub(r'\D', '', ep_name)
                            if nums and int(nums) == num and ep_url:
                                direct = ep_url
                                break
                        if direct is None and 0 < num <= len(picks) and picks[num - 1][1]:
                            direct = picks[num - 1][1]
                        if direct:
                            url = direct

            if not url:
                raise Exception('未找到播放地址')
            result['parse'] = p
            result['url'] = url
            result['header'] = self.headers
        except Exception as e:
            print(f"播放数据获取失败: {str(e)}")
            # 兜底也必须 parse=0 且 url 非空：parse=1 会令壳进入空 url 嗅探分支而崩溃
            result['parse'] = 0
            result['url'] = (id or '').strip() or self.host
            result['header'] = self.headers
        return result

    def localProxy(self, param):
        try:
            wdict = json.loads(self.d64(param['wdict']))
            url = f"{wdict['jx']}{wdict['id']}"
            data = self.fetch(url, headers=self.headers).text
            doc = pq(data)
            html = doc('script').eq(-1).text()
            url = re.search(r'src="(.*?)"', html).group(1)
            return [302, 'text/html', None, {'Location': url}]
        except Exception as e:
            print(f"代理处理失败: {str(e)}")
            return [500, 'text/plain', str(e).encode('utf-8')]

    def liveContent(self, url):
        pass

    def e64(self, text):
        try:
            text_bytes = text.encode('utf-8')
            encoded_bytes = b64encode(text_bytes)
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64编码错误: {str(e)}")
            return ""

    def d64(self, encoded_text):
        try:
            encoded_bytes = encoded_text.encode('utf-8')
            decoded_bytes = b64decode(encoded_bytes)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64解码错误: {str(e)}")
            return ""
