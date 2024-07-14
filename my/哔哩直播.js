/**
 * 影视TV 弹幕支持 
    * https://t.me/fongmi_offical/
    * https://github.com/FongMi/Release/tree/main/apk
 * 皮皮虾DMBox 弹幕支持
    * 设置 > 窗口预览 > 开启
    * https://t.me/pipixiawerun
    * vod_area:'bililivedanmu'
 * Cookie设置
    * Cookie获取方法 https://ghproxy.net/https://raw.githubusercontent.com/UndCover/PyramidStore/main/list.md
 * Cookie设置方法1: DR-PY 后台管理界面
    * CMS后台管理 > 设置中心 > 环境变量 > {"bili_cookie":"XXXXXXX","vmid":"XXXXXX"} > 保存
 * Cookie设置方法2: 手动替换Cookie
    * 底下代码 headers的
    * "Cookie":"$bili_cookie"
    * 手动替换为
    * "Cookie":"将获取的Cookie黏贴在这"
 */

var rule = {
    title:'哔哩直播',
    host:'https://api.live.bilibili.com',
    homeUrl:'/xlive/web-interface/v1/second/getUserRecommend?page=1&page_size=30&platform=web',//用于"分类获取"和"推荐获取"
    url:'/xlive/web-interface/v1/second/getList?platform=web&parent_area_id=fyclass&area_id=fyfilter&sort_type=online&page=fypage',
    class_name:'生活&网游&手游&单机游戏&娱乐&电台&虚拟主播&聊天室&知识&赛事',
    class_url:'10&2&3&6&1&5&9&14&11&13&15',
    filterable: 1,
    filter_url: '{{fl.area}}',
    filter_def:{
        10:{area:'624'},
        2:{area:'86'},
        3:{area:'35'},
        6:{area:'236'},
        1:{area:'21'},
        5:{area:'190'},
        9:{area:'744'},
        14:{area:'818'},
        11:{area:'376'},
        13:{area:'562'},
        301:{area:'301000'},
        15:{area:'814'}
    },

    detailUrl:'https://live.bilibili.com/fyid',//二级详情拼接链接(json格式用)
    // detailUrl:'https://api.live.bilibili.com/xlive/web-room/v1/playUrl/playUrl?cid=fyid&platform=h5&otype=json&quality=0',//二级详情拼接链接(json格式用)
    // searchUrl:'/x/web-interface/search/type?__refresh__=true&page=fypage&page_size=42&order=online&platform=pc&highlight=1&single_column=0&keyword=**&search_type=live&dynamic_offset=0&preload=true',
    searchUrl:'https://api.bilibili.com/x/web-interface/search/type?search_type=live&keyword=**&page=fypage',
    searchable:2,
    quickSearch:0,
    headers:{
        "User-Agent":"PC_UA",
        "Referer": "https://www.bilibili.com",
        // "Cookie":"$bili_cookie"
        "Cookie":"https://ghproxy.net/https://raw.githubusercontent.com/FongMi/CatVodSpider/main/txt/cookie.txt"
    },
    timeout:3000,
    limit:8,
    play_parse:true,
    // play_json:[{re:'*', json:{jx:0, parse:1,header:JSON.stringify({"user-agent":"Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI 9 Build/PKQ1.181121.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/12.5.5.1035 Mobile Safari/537.36"})}}],
    // play_json:[{re:'*', json:{jx:0, parse:1,header:JSON.stringify({"user-agent":"uc_ua"})}}],
    // play_json:0,
    lazy:`js:
        let ids = input.split('_');
        let dan = 'https://api.bilibili.com/x/v1/dm/list.so?oid=' + ids[1];
        let result = {};
        let iurl = 'https://api.live.bilibili.com/room/v1/Room/playUrl?cid=' + ids[1] + '&' + ids[0];
        let html = request(iurl);
        let jRoot = JSON.parse(html);
        let jo = jRoot['data'];
        let ja = jo['durl'];
        let purl = '';
        if (ja.length > 0) {
            purl = ja[0]['url']
        }
        result['parse'] = 0;
        result['playUrl'] = '';
        result['url'] = unescape(purl);
        result['header'] = {
            Referer: 'https://live.bilibili.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36'
        };
        result['danmaku'] = dan;
        if (/h5/.test(ids[0])) {
            result['contentType'] = '';
            input = result
        } else {
            result['contentType'] = 'video/x-flv';
            input = result
        }
    `,
    double:false,
    推荐:'*',
    一级:'json:data.list;title;system_cover;uname;roomid',
    // 二级:'*',
    二级:"js:let aid=input.match(/\\/(\\d+)/)[1];log(aid);let html=request('https://api.live.bilibili.com/room/v1/Room/get_info?room_id='+aid);let jo=JSON.parse(html).data;let title=jo['title'];let pic=jo['keyframe'];let desc=jo['description'];let dire=jo['uid'];let typeName=jo['area_name'];let remark='在线人数:'+jo['online'];let vod={vod_id:aid,vod_name:title,vod_pic:pic,type_name:typeName,vod_area:'bililivedanmu',vod_remarks:remark,vod_actor:'直播间id-'+aid,vod_director:dire,vod_content:desc};vod['vod_play_from']='B站';vod['vod_play_url']='flv线路原画$platform=web&quality=4_'+aid+'#flv线路高清$platform=web&quality=3_'+aid+'#h5线路原画$platform=h5&quality=4_'+aid+'#h5线路高清$platform=h5&quality=3_'+aid;VOD=vod;",
    // 搜索:'json:data.result.live_room;title;cover;uname;roomid',
    搜索:'js:let html=request(input);let msg=JSON.parse(html).message;if(msg!=="0"){VODS=[{vod_name:KEY+"➢"+msg,vod_id:"no_data",vod_remarks:"别点,缺少bili_cookie",vod_pic:"https://ghproxy.net/https://raw.githubusercontent.com/hjdhnx/dr_py/main/404.jpg"}]}else{let videos=[];let vodList=JSON.parse(html).data.result.live_room;vodList.forEach(function(vod){let aid=vod["roomid"];let title="直播间："+vod["title"].replace(\'<em class="keyword">\',"").replace("</em>","");let img="https:"+vod["user_cover"];let remark=vod["watched_show"]["text_small"]+"  "+vod["uname"];videos.push({vod_id:aid,vod_name:title,vod_pic:img,vod_remarks:remark})});VODS=videos}',
    // 预处理:'if(rule_fetch_params.headers.Cookie.startsWith("http")){rule_fetch_params.headers.Cookie=fetch(rule_fetch_params.headers.Cookie);setItem(RULE_CK,cookie)};log(rule_fetch_params.headers.Cookie)',
}
