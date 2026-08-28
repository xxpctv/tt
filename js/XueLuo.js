/**
 * XueLuo Spider for CatVod / OK影视
 * ❄️雪咯音乐 v7.0 - 完整独立版本
 *
 * 基于 aidaox-20260825-214819.jar 逆向分析
 * 独立于 JAR 运行，功能完整
 *
 * 支持 5 个音源:
 *   kw(酷我)、kg(酷狗)、tx(腾讯)、wy(网易)、mg(咪咕)
 *
 * 功能:
 *   - 多音源并行搜索
 *   - 排行榜浏览
 *   - 播放URL获取(念心PHP API + Gateway双模式)
 *   - 自动音质降级
 *
 * 使用方法 (CatVod 配置):
 *   {
 *     "key": "XueLuo",
 *     "name": "❄️雪咯音乐",
 *     "type": 3,
 *     "api": "./XueLuo.js",
 *     "searchable": 1,
 *     "quickSearch": 0,
 *     "filterable": 0,
 *     "changeable": 0
 *   }
 */

// ============================================================
// 配置区
// ============================================================

var CONFIG = {
  // 音源定义
  sources: {
    kw: { name: '酷我', shortName: 'KW', id: 'kw', apiName: 'kuwo' },
    kg: { name: '酷狗', shortName: 'KG', id: 'kg', apiName: 'kugou' },
    tx: { name: '腾讯', shortName: 'TX', id: 'tx', apiName: 'qq' },
    wy: { name: '网易', shortName: 'WY', id: 'wy', apiName: 'netease' },
    mg: { name: '咪咕', shortName: 'MG', id: 'mg', apiName: 'migu' }
  },

  // 念心音源 PHP API 基础地址
  musicApi: 'https://mcp.nianxinxz.com/share/ceshi',

  // 音质映射 (CatVod → PHP level 参数)
  qualityMap: {
    '128k': 'standard',
    '320k': 'exhigh',
    'flac': 'lossless',
    'flac24bit': 'hires'
  },

  // 各音源支持的音质 (从 user-api-preload.js 提取)
  sourceQualities: {
    kw: ['128k', '320k', 'flac', 'flac24bit'],
    kg: ['128k', '320k', 'flac', 'flac24bit'],
    tx: ['128k', '320k', 'flac', 'flac24bit'],
    wy: ['128k', '320k', 'flac', 'flac24bit'],
    mg: ['128k', '320k', 'flac', 'flac24bit']
  },

  // 请求配置
  request: {
    timeout: 15000,
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
  }
};

// ============================================================
// 排行榜配置 (从 XueLuoMeta.java 反编译提取 + 解码)
// ============================================================

var RANK_BOARDS = {
  // 网易 (wy) - 8个榜单
  wy: [
    { id: '50411', name: '飙升榜' },
    { id: '50413', name: '新歌榜' },
    { id: '50414', name: '原创榜' },
    { id: '50415', name: '电音榜' },
    { id: '50416', name: '古典榜' },
    { id: '50417', name: '国风电音榜' },
    { id: '50418', name: '说唱榜' },
    { id: '50419', name: '流行榜' }
  ],

  // 腾讯 (tx) - 8个榜单
  tx: [
    { id: '4', name: '新歌榜' },
    { id: '26', name: '热歌榜' },
    { id: '27', name: '飙升榜' },
    { id: '62', name: '原创榜' },
    { id: '28', name: '说唱榜' },
    { id: '60', name: '民谣榜' },
    { id: '5', name: '摇滚榜' },
    { id: '3', name: '电子榜' }
  ],

  // 酷我 (kw) - 12个榜单
  kw: [
    { id: '93', name: '飙升榜' },
    { id: '16', name: 'TOP500' },
    { id: '17', name: 'ACG榜' },
    { id: '158', name: '说唱榜' },
    { id: '145', name: '摇滚榜' },
    { id: '187', name: '电子榜' },
    { id: '26', name: '民谣榜' },
    { id: '104', name: '轻音乐榜' },
    { id: '182', name: 'DJ榜' },
    { id: '184', name: '儿歌榜' },
    { id: '183', name: '戏曲榜' },
    { id: '94', name: '爵士榜' }
  ],

  // 酷狗 (kg) - 11个榜单
  kg: [
    { id: '8888', name: '飙升榜' },
    { id: '6666', name: '热歌榜' },
    { id: '23784', name: '新歌榜' },
    { id: '21101', name: '原创榜' },
    { id: '24971', name: '古典榜' },
    { id: '52144', name: '电音榜' },
    { id: '33161', name: '欧美热歌榜' },
    { id: '33165', name: '国风榜' },
    { id: '33166', name: '日语流行榜' },
    { id: '33160', name: '韩语流行榜' },
    { id: '31308', name: '粤语流行榜' }
  ],

  // 咪咕 (mg) - 7个榜单
  mg: [
    { id: '1', name: '中国移动排行榜' },
    { id: '2', name: '最热榜单' },
    { id: '3', name: '原创榜单' },
    { id: '4', name: '本地榜单' },
    { id: '5', name: '欧美榜单' },
    { id: '6', name: '日韩榜单' },
    { id: '7', name: '古风榜单' }
  ]
};

// ============================================================
// 工具函数
// ============================================================

function safeStr(str) {
  return (str == null) ? '' : str.toString();
}

function trimStr(str) {
  return safeStr(str).trim();
}

function joinArtists(artists) {
  if (!Array.isArray(artists) || artists.length === 0) return '';
  var names = [];
  for (var i = 0; i < artists.length; i++) {
    if (artists[i] && artists[i].name) {
      names.push(artists[i].name);
    }
  }
  return names.join('、');
}

// ============================================================
// HTTP 请求封装 (CatVod 兼容 + fetch 降级)
// ============================================================

/**
 * HTTP 请求 - 优先使用 lx.request (CatVod 内部), 降级到 fetch
 */
async function httpRequest(url, options) {
  options = options || {};
  var method = options.method || 'GET';
  var headers = options.headers || {};
  var body = options.body || null;
  var timeout = options.timeout || CONFIG.request.timeout;

  // 合并默认 headers
  var mergedHeaders = {};
  for (var k in headers) {
    if (headers.hasOwnProperty(k)) {
      mergedHeaders[k] = headers[k];
    }
  }
  if (!mergedHeaders['User-Agent']) {
    mergedHeaders['User-Agent'] = CONFIG.request.userAgent;
  }
  if (!mergedHeaders['Accept']) {
    mergedHeaders['Accept'] = 'application/json, text/plain, */*';
  }

  // 方式1: 使用 lx.request (CatVod 原生, 可绕过 CORS)
  if (globalThis && globalThis.lx && typeof globalThis.lx.request === 'function') {
    try {
      var result = await new Promise(function(resolve, reject) {
        var timer = setTimeout(function() { reject(new Error('timeout')); }, timeout);
        globalThis.lx.request(url, {
          method: method,
          headers: mergedHeaders,
          body: body,
          timeout: timeout
        }, function(err, response, respBody) {
          clearTimeout(timer);
          if (err) {
            reject(err);
          } else {
            resolve({ response: response, body: respBody });
          }
        });
      });

      // 处理返回
      if (result && result.body) {
        try { return JSON.parse(result.body); } catch(e) { return result.body; }
      }
      if (result && result.response && result.response.body) {
        try { return JSON.parse(result.response.body); } catch(e) { return result.response.body; }
      }
      return result;
    } catch (e) {
      // 降级到 fetch
    }
  }

  // 方式2: 使用 fetch
  try {
    var fetchOptions = {
      method: method,
      headers: mergedHeaders
    };
    if (body) {
      fetchOptions.body = (typeof body === 'string') ? body : JSON.stringify(body);
    }

    var response = await fetch(url, fetchOptions);
    var text = typeof response.text === 'function'
      ? await response.text()
      : (response.body || '');

    try { return JSON.parse(text); } catch(e) { return text; }
  } catch (e2) {
    return null;
  }
}

/**
 * HTTP GET
 */
async function httpGet(url, headers) {
  return httpRequest(url, { method: 'GET', headers: headers || {} });
}

/**
 * HTTP POST
 */
async function httpPost(url, body, headers) {
  return httpRequest(url, {
    method: 'POST',
    headers: Object.assign({ 'Content-Type': 'application/json' }, headers || {}),
    body: body
  });
}

// ============================================================
// JSONP 解析
// ============================================================

function parseJSONP(text) {
  if (typeof text !== 'string') return text;
  var match = text.match(/^[^(]+\((.*)\)\s*;?\s*$/s);
  if (match) {
    try { return JSON.parse(match[1]); } catch(e) { return text; }
  }
  try { return JSON.parse(text); } catch(e2) { return text; }
}

// ============================================================
// MD5 实现 (用于咪咕搜索签名)
// ============================================================

function md5(str) {
  function safeAdd(x, y) {
    var lsw = (x & 0xFFFF) + (y & 0xFFFF);
    var msw = (x >> 16) + (y >> 16) + (lsw >> 16);
    return (msw << 16) | (lsw & 0xFFFF);
  }
  function bitRol(num, cnt) {
    return (num << cnt) | (num >>> (32 - cnt));
  }
  function md5cmn(q, a, b, x, s, t) {
    return safeAdd(bitRol(safeAdd(safeAdd(a, q), safeAdd(x, t)), s), b);
  }
  function md5ff(a, b, c, d, x, s, t) { return md5cmn((b & c) | ((~b) & d), a, b, x, s, t); }
  function md5gg(a, b, c, d, x, s, t) { return md5cmn((b & d) | (c & (~d)), a, b, x, s, t); }
  function md5hh(a, b, c, d, x, s, t) { return md5cmn(b ^ c ^ d, a, b, x, s, t); }
  function md5ii(a, b, c, d, x, s, t) { return md5cmn(c ^ (b | (~d)), a, b, x, s, t); }
  function binlMD5(x, len) {
    x[len >> 5] |= 0x80 << (len % 32);
    x[(((len + 64) >>> 9) << 4) + 14] = len;
    var a = 1732584193, b = -271733879, c = -1732584194, d = 271733878;
    for (var i = 0; i < x.length; i += 16) {
      var olda = a, oldb = b, oldc = c, oldd = d;
      a = md5ff(a,b,c,d,x[i],7,-680876936); d = md5ff(d,a,b,c,x[i+1],12,-389564586); c = md5ff(c,d,a,b,x[i+2],17,606105819); b = md5ff(b,c,d,a,x[i+3],22,-1044525330);
      a = md5ff(a,b,c,d,x[i+4],7,-176418897); d = md5ff(d,a,b,c,x[i+5],12,1200080426); c = md5ff(c,d,a,b,x[i+6],17,-1473231341); b = md5ff(b,c,d,a,x[i+7],22,-45705983);
      a = md5ff(a,b,c,d,x[i+8],7,1770035416); d = md5ff(d,a,b,c,x[i+9],12,-1958414417); c = md5ff(c,d,a,b,x[i+10],17,-42063); b = md5ff(b,c,d,a,x[i+11],22,-1990404162);
      a = md5ff(a,b,c,d,x[i+12],7,1804603682); d = md5ff(d,a,b,c,x[i+13],12,-40341101); c = md5ff(c,d,a,b,x[i+14],17,-1502002290); b = md5ff(b,c,d,a,x[i+15],22,1236535329);
      a = md5gg(a,b,c,d,x[i+1],5,-165796510); d = md5gg(d,a,b,c,x[i+6],9,-1069501632); c = md5gg(c,d,a,b,x[i+11],14,643717713); b = md5gg(b,c,d,a,x[i],20,-373897302);
      a = md5gg(a,b,c,d,x[i+5],5,-701558691); d = md5gg(d,a,b,c,x[i+10],9,38016083); c = md5gg(c,d,a,b,x[i+15],14,-660478335); b = md5gg(b,c,d,a,x[i+4],20,-405537848);
      a = md5gg(a,b,c,d,x[i+9],5,568446438); d = md5gg(d,a,b,c,x[i+14],9,-1019803690); c = md5gg(c,d,a,b,x[i+3],14,-187363961); b = md5gg(b,c,d,a,x[i+8],20,1163531501);
      a = md5gg(a,b,c,d,x[i+13],5,-1444681467); d = md5gg(d,a,b,c,x[i+2],9,-51403784); c = md5gg(c,d,a,b,x[i+7],14,1735328473); b = md5gg(b,c,d,a,x[i+12],20,-1926607734);
      a = md5hh(a,b,c,d,x[i+5],4,-378558); d = md5hh(d,a,b,c,x[i+8],11,-2022574463); c = md5hh(c,d,a,b,x[i+11],16,1839030562); b = md5hh(b,c,d,a,x[i+14],23,-35309556);
      a = md5hh(a,b,c,d,x[i+1],4,-1530992060); d = md5hh(d,a,b,c,x[i+4],11,1272893353); c = md5hh(c,d,a,b,x[i+7],16,-155497632); b = md5hh(b,c,d,a,x[i+10],23,-1094730640);
      a = md5hh(a,b,c,d,x[i+13],4,681279174); d = md5hh(d,a,b,c,x[i],11,-358537222); c = md5hh(c,d,a,b,x[i+3],16,-722521979); b = md5hh(b,c,d,a,x[i+6],23,76029189);
      a = md5hh(a,b,c,d,x[i+9],4,-640364487); d = md5hh(d,a,b,c,x[i+12],11,-421815835); c = md5hh(c,d,a,b,x[i+15],16,530742520); b = md5hh(b,c,d,a,x[i+2],23,-995338651);
      a = md5ii(a,b,c,d,x[i],6,-198630844); d = md5ii(d,a,b,c,x[i+7],10,1126891415); c = md5ii(c,d,a,b,x[i+14],15,-1416354905); b = md5ii(b,c,d,a,x[i+5],21,-57434055);
      a = md5ii(a,b,c,d,x[i+12],6,1700485571); d = md5ii(d,a,b,c,x[i+3],10,-1894986606); c = md5ii(c,d,a,b,x[i+10],15,-1051523); b = md5ii(b,c,d,a,x[i+1],21,-2054922799);
      a = md5ii(a,b,c,d,x[i+8],6,1873313359); d = md5ii(d,a,b,c,x[i+15],10,-30611744); c = md5ii(c,d,a,b,x[i+6],15,-1560198380); b = md5ii(b,c,d,a,x[i+13],21,1309151649);
      a = md5ii(a,b,c,d,x[i+4],6,-145523070); d = md5ii(d,a,b,c,x[i+11],10,-1120210379); c = md5ii(c,d,a,b,x[i+2],15,718787259); b = md5ii(b,c,d,a,x[i+9],21,-343485551);
      a = safeAdd(a, olda); b = safeAdd(b, oldb); c = safeAdd(c, oldc); d = safeAdd(d, oldd);
    }
    return [a, b, c, d];
  }
  function binl2rstr(input) {
    var output = '';
    var length32 = input.length * 32;
    for (var i = 0; i < length32; i += 8) {
      output += String.fromCharCode((input[i >> 5] >>> (i % 32)) & 0xFF);
    }
    return output;
  }
  function rstr2binl(input) {
    var output = [];
    for (var i = 0; i < input.length * 8; i += 8) {
      output[i >> 5] = (output[i >> 5] || 0) | ((input.charCodeAt(i / 8) & 0xFF) << (i % 32));
    }
    return output;
  }
  function rstrMD5(s) { return binl2rstr(binlMD5(rstr2binl(s), s.length * 8)); }
  function rstr2hex(input) {
    var hexTab = '0123456789abcdef';
    var output = '';
    for (var i = 0; i < input.length; i++) {
      var x = input.charCodeAt(i);
      output += hexTab.charAt((x >>> 4) & 0x0F) + hexTab.charAt(x & 0x0F);
    }
    return output;
  }
  function str2rstrUTF8(input) { return unescape(encodeURIComponent(input)); }
  function rawMD5(s) { return rstrMD5(str2rstrUTF8(s)); }
  function hexMD5(s) { return rstr2hex(rawMD5(s)); }
  return hexMD5(str);
}

// ============================================================
// 搜索功能 - 各音源官方 API
// ============================================================

/**
 * 酷我搜索
 */
async function searchKuWo(keyword, page) {
  page = page || 1;
  var results = [];
  try {
    var url = 'https://search.kuwo.cn/r.s'
      + '?client=kt'
      + '&all=' + encodeURIComponent(keyword)
      + '&pn=' + page
      + '&rn=30'
      + '&uid=794762570'
      + '&ver=kwplayer_ar_99.99.99.99'
      + '&vipver=1'
      + '&show_copyright_off=1'
      + '&newver=1'
      + '&ft=music'
      + '&cluster=0'
      + '&strategy=2012'
      + '&encoding=utf8'
      + '&rformat=json'
      + '&vermerge=1'
      + '&mobi=1';

    var rawData = await httpGet(url, {
      'User-Agent': 'KuWoMusic/11.9.6 Android',
      'Referer': 'https://www.kuwo.cn/'
    });

    var data = rawData;
    if (typeof rawData === 'string') data = parseJSONP(rawData);

    if (data && Array.isArray(data.abslist)) {
      for (var i = 0; i < data.abslist.length; i++) {
        var song = data.abslist[i];
        var rid = safeStr(song.MUSICRID);
        if (!rid) continue;
        results.push({
          title: safeStr(song.SONGNAME),
          artist: safeStr(song.ARTIST),
          album: safeStr(song.ALBUM),
          duration: 0,
          source: 'kw',
          songmid: rid,
          quality: '320k',
          picUrl: safeStr(song.ALBUMART) || safeStr(song.pic)
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

/**
 * 酷狗搜索
 */
async function searchKuGou(keyword, page) {
  page = page || 1;
  var results = [];
  try {
    var url = 'https://songsearch.kugou.com/song_search_v2'
      + '?keyword=' + encodeURIComponent(keyword)
      + '&page=' + page
      + '&pagesize=30'
      + '&userid=0'
      + '&clientver='
      + '&platform=WebFilter'
      + '&filter=2'
      + '&iscorrection=1'
      + '&privilege_filter=0'
      + '&area_code=1';

    var data = await httpGet(url, {
      'User-Agent': 'Mozilla/5.0',
      'Referer': 'https://www.kugou.com/'
    });

    if (data && data.data && Array.isArray(data.data.lists)) {
      for (var i = 0; i < data.data.lists.length; i++) {
        var song = data.data.lists[i];
        var hash = safeStr(song.FileHash);
        if (!hash) continue;
        results.push({
          title: safeStr(song.SongName),
          artist: safeStr(song.SingerName),
          album: safeStr(song.AlbumName),
          duration: 0,
          source: 'kg',
          songmid: hash,
          quality: '320k',
          picUrl: safeStr(song.Image) || safeStr(song.AlbumLogo)
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

/**
 * 腾讯搜索
 */
async function searchTencent(keyword, page) {
  page = page || 1;
  var results = [];
  try {
    var url = 'https://c.y.qq.com/soso/fcgi-bin/client_search_cp'
      + '?p=' + page
      + '&n=30'
      + '&w=' + encodeURIComponent(keyword)
      + '&format=json'
      + '&inCharset=utf8'
      + '&outCharset=utf-8'
      + '&notice=0'
      + '&platform=yqq.json'
      + '&needNewCode=0'
      + '&t=0'
      + '&aggr=1'
      + '&cr=1'
      + '&lossless=0'
      + '&flag_qc=0';

    var rawData = await httpGet(url, {
      'Referer': 'https://y.qq.com/',
      'Origin': 'https://y.qq.com'
    });

    var data = rawData;
    if (typeof rawData === 'string') data = parseJSONP(rawData);

    if (data && data.data && data.data.song && Array.isArray(data.data.song.list)) {
      for (var i = 0; i < data.data.song.list.length; i++) {
        var song = data.data.song.list[i];
        var songmid = safeStr(song.songmid);
        if (!songmid) continue;
        var singers = joinArtists(song.singer);
        var albummid = safeStr(song.albummid);
        var picUrl = albummid
          ? 'https://y.gtimg.cn/music/photo_new/T002R500x500M000' + albummid + '.jpg'
          : '';
        results.push({
          title: safeStr(song.songname),
          artist: singers,
          album: safeStr(song.albumname),
          duration: song.interval ? (song.interval * 1000) : 0,
          source: 'tx',
          songmid: songmid,
          quality: '320k',
          picUrl: picUrl
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

/**
 * 网易搜索
 */
async function searchNetEase(keyword, page) {
  page = page || 1;
  var results = [];
  try {
    var offset = (page - 1) * 30;
    var url = 'https://music.163.com/api/search/get/web'
      + '?s=' + encodeURIComponent(keyword)
      + '&type=1'
      + '&offset=' + offset
      + '&total=true'
      + '&limit=30';

    var data = await httpGet(url, {
      'Referer': 'https://music.163.com/',
      'Origin': 'https://music.163.com'
    });

    if (data && data.result && Array.isArray(data.result.songs)) {
      for (var i = 0; i < data.result.songs.length; i++) {
        var song = data.result.songs[i];
        var id = safeStr(song.id);
        if (!id) continue;
        var artists = joinArtists(song.artists || song.ar);
        var picUrl = safeStr(song.album ? song.album.picUrl : '');
        results.push({
          title: safeStr(song.name),
          artist: artists,
          album: safeStr(song.album ? song.album.name : ''),
          duration: song.duration || 0,
          source: 'wy',
          songmid: id,
          quality: '320k',
          picUrl: picUrl
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

/**
 * 咪咕搜索
 */
async function searchMigu(keyword, page) {
  page = page || 1;
  var results = [];
  try {
    var timestamp = Date.now().toString();
    var signKey = '6cdc72a439cef99a3418d2a78aa28c73'
      + 'yyapp2d16148780a1dcc7408e06336b98cfd50963B7AA0D21511ED807EE5846EC87D20';
    var signText = keyword + signKey + timestamp;
    var sign = md5(signText);

    var searchSwitch = encodeURIComponent(JSON.stringify({
      song: 1, album: 0, singer: 0, tagSong: 1,
      mvSong: 0, bestShow: 1, songlist: 0, lyricSong: 0
    }));

    var url = 'https://jadeite.migu.cn/music_search/v3/search/searchAll'
      + '?isCorrect=0'
      + '&isCopyright=1'
      + '&searchSwitch=' + searchSwitch
      + '&pageSize=30'
      + '&text=' + encodeURIComponent(keyword)
      + '&pageNo=' + page
      + '&sort=0'
      + '&sid=USS';

    var data = await httpGet(url, {
      'User-Agent': 'A_music_3.6.1',
      'channel': '0146921',
      'timestamp': timestamp,
      'sign': sign
    });

    var songList = null;
    if (data && data.data) {
      if (Array.isArray(data.data)) songList = data.data;
      else if (Array.isArray(data.data.songList)) songList = data.data.songList;
      else if (Array.isArray(data.data.songlist)) songList = data.data.songlist;
    }

    if (songList) {
      for (var i = 0; i < songList.length; i++) {
        var song = songList[i];
        var id = safeStr(song.songId || song.songid || song.id);
        if (!id) continue;
        results.push({
          title: safeStr(song.songName || song.name || song.songname),
          artist: safeStr(song.singer || song.artistName),
          album: safeStr(song.albumName || song.album),
          duration: 0,
          source: 'mg',
          songmid: id,
          quality: '320k',
          picUrl: safeStr(song.pic || song.albumPic || song.poster)
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

// ============================================================
// 排行榜功能 - 各音源官方 API
// ============================================================

/**
 * 酷我排行榜
 */
async function getKuWoRankSongs(rankId, page) {
  page = page || 1;
  var results = [];

  // 方式1: Web API
  try {
    var url = 'https://www.kuwo.cn/api/www/bang/bang/musicList'
      + '?bangId=' + rankId;

    var data = await httpGet(url, {
      'User-Agent': 'KuWoMusic/11.9.6 Android',
      'Referer': 'https://www.kuwo.cn/rankList',
      'Cookie': 'kw_token=' + Math.random().toString(36).substr(2)
    });

    if (data && data.data && Array.isArray(data.data.musicList)) {
      var list = data.data.musicList;
      var start = (page - 1) * 30;
      var end = Math.min(start + 30, list.length);
      for (var i = start; i < end; i++) {
        var song = list[i];
        var rid = safeStr(song.id);
        if (!rid) continue;
        results.push({
          title: safeStr(song.name),
          artist: safeStr(song.artist),
          album: safeStr(song.album),
          duration: 0,
          source: 'kw',
          songmid: rid,
          quality: '320k',
          picUrl: safeStr(song.pic)
        });
      }
    }
  } catch (e) { /* 尝试备用方式 */ }

  // 方式2: 备用 HTTP API
  if (results.length === 0) {
    try {
      var url2 = 'http://nplserver.kuwo.cn/pl.svc'
        + '?op=getlistinfo'
        + '&pid=' + rankId
        + '&pn=0'
        + '&rn=100'
        + '&encode=utf8'
        + '&keyset=pl2012'
        + '&identity=kuwo'
        + '&pcmp4=1'
        + '&vipver=MUSIC_9.0.5.0_W1'
        + '&newver=1';

      var data2 = await httpGet(url2, {
        'User-Agent': 'KuWoMusic/11.9.6 Android'
      });

      var list2 = null;
      if (data2 && Array.isArray(data2.abslist)) list2 = data2.abslist;
      else if (data2 && Array.isArray(data2.musiclist)) list2 = data2.musiclist;

      if (list2 && list2.length > 0) {
        for (var j = 0; j < list2.length; j++) {
          var s = list2[j];
          results.push({
            title: safeStr(s.SONGNAME || s.name),
            artist: safeStr(s.ARTIST || s.singer),
            album: safeStr(s.ALBUM || s.album),
            duration: 0,
            source: 'kw',
            songmid: safeStr(s.MUSICRID || s.rid),
            quality: '320k',
            picUrl: safeStr(s.pic)
          });
        }
      }
    } catch (e2) { /* 返回空 */ }
  }
  return results;
}

/**
 * 酷狗排行榜
 */
async function getKuGouRankSongs(rankId, page) {
  page = page || 1;
  var results = [];
  try {
    var url = 'https://m.kugou.com/plist/list/' + rankId + '/?json=true';

    var data = await httpGet(url, {
      'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3)',
      'Referer': 'https://m.kugou.com/'
    });

    if (data && data.data && Array.isArray(data.data.songlist)) {
      var list = data.data.songlist;
      var start = (page - 1) * 30;
      var end = Math.min(start + 30, list.length);
      for (var i = start; i < end; i++) {
        var song = list[i];
        var hash = safeStr(song.hash);
        if (!hash) continue;
        results.push({
          title: safeStr(song.songname),
          artist: safeStr(song.singer),
          album: safeStr(song.album),
          duration: 0,
          source: 'kg',
          songmid: hash,
          quality: '320k',
          picUrl: safeStr(song.pic)
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

/**
 * 腾讯排行榜
 */
async function getTencentRankSongs(rankId, page) {
  page = page || 1;
  var results = [];
  try {
    var jsonData = JSON.stringify({
      comm: { uin: 0, format: 'json', ct: 20, cv: 1859 },
      toplist: {
        module: 'musicToplist.ToplistInfoServer',
        method: 'GetDetail',
        param: {
          topId: parseInt(rankId),
          offset: 0,
          num: 100,
          period: '',
          context: ''
        }
      }
    });

    var url = 'https://u.y.qq.com/cgi-bin/musicu.fcg?data='
      + encodeURIComponent(jsonData);

    var data = await httpGet(url, {
      'Referer': 'https://y.qq.com/',
      'Origin': 'https://y.qq.com'
    });

    // 查找 songInfoList
    var songList = null;
    if (data && data.toplist && data.toplist.data) {
      songList = data.toplist.data.songInfoList || null;
    }

    if (songList) {
      var start = (page - 1) * 30;
      var end = Math.min(start + 30, songList.length);
      for (var i = start; i < end; i++) {
        var song = songList[i];
        var mid = safeStr(song.mid);
        if (!mid) continue;
        var singers = joinArtists(song.singer);
        var albumMid = '';
        var albumName = '';
        if (song.album && typeof song.album === 'object') {
          albumMid = safeStr(song.album.mid || song.albumMid);
          albumName = safeStr(song.album.name);
        }
        var picUrl = albumMid
          ? 'https://y.gtimg.cn/music/photo_new/T002R500x500M000' + albumMid + '.jpg'
          : '';
        results.push({
          title: safeStr(song.name),
          artist: singers,
          album: albumName,
          duration: song.interval ? (song.interval * 1000) : 0,
          source: 'tx',
          songmid: mid,
          quality: '320k',
          picUrl: picUrl
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

/**
 * 网易排行榜
 */
async function getNetEaseRankSongs(rankId, page) {
  page = page || 1;
  var results = [];
  try {
    var url = 'https://music.163.com/api/playlist/detail?id=' + rankId;

    var data = await httpGet(url, {
      'Referer': 'https://music.163.com/',
      'Origin': 'https://music.163.com',
      'User-Agent': 'Mozilla/5.0'
    });

    var tracks = null;
    if (data && data.playlist && Array.isArray(data.playlist.tracks)) {
      tracks = data.playlist.tracks;
    } else if (data && data.result && Array.isArray(data.result.tracks)) {
      tracks = data.result.tracks;
    }

    if (tracks && tracks.length > 0) {
      var start = (page - 1) * 30;
      var end = Math.min(start + 30, tracks.length);
      for (var i = start; i < end; i++) {
        var song = tracks[i];
        var id = safeStr(song.id);
        if (!id) continue;
        var artists = joinArtists(song.artists || song.ar);
        var picUrl = safeStr(song.album ? song.album.picUrl : '');
        results.push({
          title: safeStr(song.name),
          artist: artists,
          album: safeStr(song.album ? song.album.name : ''),
          duration: song.duration || 0,
          source: 'wy',
          songmid: id,
          quality: '320k',
          picUrl: picUrl
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

/**
 * 咪咕排行榜
 */
async function getMiguRankSongs(rankId, page) {
  page = page || 1;
  var results = [];
  try {
    var url = 'https://app.c.nf.migu.cn/pc/bmw/page-data/playlist-square-recommend/v1.0'
      + '?templateVersion=2'
      + '&pageNo=' + page;

    var data = await httpGet(url, {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    });

    var songList = null;
    if (data && data.data && Array.isArray(data.data.contents)) {
      var contents = data.data.contents;
      for (var c = 0; c < contents.length; c++) {
        var content = contents[c];
        if (content.songList && Array.isArray(content.songList)) {
          if (!songList) songList = [];
          songList = songList.concat(content.songList);
        }
      }
    }

    if (songList && songList.length > 0) {
      var start = (page - 1) * 30;
      var end = Math.min(start + 30, songList.length);
      for (var i = start; i < end; i++) {
        var song = songList[i];
        var id = safeStr(song.songId || song.songid || song.id);
        if (!id) continue;
        results.push({
          title: safeStr(song.songName || song.name),
          artist: safeStr(song.singer || song.artistName),
          album: safeStr(song.albumName || song.album),
          duration: 0,
          source: 'mg',
          songmid: id,
          quality: '320k',
          picUrl: safeStr(song.pic || song.poster)
        });
      }
    }
  } catch (e) { /* 返回空 */ }
  return results;
}

// ============================================================
// 播放 URL 获取 - 念心PHP API + Gateway 双模式
// ============================================================

/**
 * 获取音乐播放 URL
 * 基于 nianxin.js + XueLuoGateway.java 逆向分析
 *
 * 调用流程:
 * 1. 尝试念心 PHP API (heibox模式)
 * 2. 降级到 juhe 模式
 * 3. 返回空
 *
 * @param {string} source - 音源 (kw/kg/tx/wy/mg)
 * @param {string} songmid - 歌曲 ID
 * @param {string} quality - 音质 (128k/320k/flac/flac24bit)
 * @returns {Promise<string>} 播放 URL
 */
async function getPlayUrl(source, songmid, quality) {
  if (!CONFIG.sources[source]) return '';
  if (!songmid) return '';

  quality = quality || '320k';

  // 检查音源是否支持该音质，不支持则降级
  var supportedQualities = CONFIG.sourceQualities[source];
  if (supportedQualities.indexOf(quality) === -1) {
    // 降级到支持的最高音质
    if (supportedQualities.indexOf('flac') !== -1) {
      quality = 'flac';
    } else if (supportedQualities.indexOf('320k') !== -1) {
      quality = '320k';
    } else {
      quality = supportedQualities[supportedQualities.length - 1];
    }
  }

  var level = CONFIG.qualityMap[quality] || 'exhigh';

  // 方式1: 念心 PHP API (heibox模式 - 点播)
  var url1 = buildHeiboxUrl(source, songmid, level);
  var result = await tryPhpApi(url1);
  if (result) return result;

  // 方式2: juhe模式 (聚合)
  var url2 = buildJuheUrl(source, songmid, quality);
  result = await tryPhpApi(url2);
  if (result) return result;

  // 方式3: 降级 - 直接返回PHP API URL (CatVod会自动解析)
  return buildHeiboxUrl(source, songmid, level);
}

/**
 * 构建 heibox 模式 URL (念心PHP API)
 * 基于 nianxin.js 中各音源 musicUrl 函数分析
 */
function buildHeiboxUrl(source, songmid, level) {
  switch (source) {
    case 'kg':
      // 酷狗: /kg.php?hash={songmid}&level={quality}&type=mp3
      return CONFIG.musicApi + '/kg.php'
        + '?hash=' + encodeURIComponent(songmid)
        + '&level=' + level
        + '&type=mp3';

    case 'kw':
      // 酷我: /kw.php?id={songmid}&level={quality} (无type参数)
      return CONFIG.musicApi + '/kw.php'
        + '?id=' + encodeURIComponent(songmid)
        + '&level=' + level;

    case 'tx':
      // 腾讯: /tx.php?id={songmid}&level={quality}&type=mp3
      return CONFIG.musicApi + '/tx.php'
        + '?id=' + encodeURIComponent(songmid)
        + '&level=' + level
        + '&type=mp3';

    case 'wy':
      // 网易: /wy.php?id={songmid}&level={quality}&type=mp3
      return CONFIG.musicApi + '/wy.php'
        + '?id=' + encodeURIComponent(songmid)
        + '&level=' + level
        + '&type=mp3';

    case 'mg':
      // 咪咕: /mg.php?id={songmid}&level={quality}&type=mp3
      return CONFIG.musicApi + '/mg.php'
        + '?id=' + encodeURIComponent(songmid)
        + '&level=' + level
        + '&type=mp3';

    default:
      return '';
  }
}

/**
 * 构建 juhe 模式 URL (聚合)
 */
function buildJuheUrl(source, songmid, quality) {
  return CONFIG.musicApi + '/' + source + '.php'
    + '?id=' + encodeURIComponent(songmid)
    + '&type=juhe';
}

/**
 * 尝试 PHP API 请求并解析返回
 * 念心 API 返回格式:
 *   {code: 0, data: {url: "https://..."}}
 *   {code: 200, data: "https://..."}
 *   {code: 200, data: {url: "https://..."}}
 *   直接返回 URL 字符串
 */
async function tryPhpApi(url) {
  try {
    var headers = {
      'User-Agent': '念心音源/1.0.2',
      'Referer': 'https://mcp.nianxinxz.com/'
    };

    var data = await httpGet(url, headers);

    if (!data) return '';

    // 如果返回的是字符串
    if (typeof data === 'string') {
      if (/^https?:\/\//.test(data)) return data;
      try { data = JSON.parse(data); } catch(e) { return ''; }
    }

    // 解析 JSON 返回
    if (data && typeof data === 'object') {
      // 格式1: {code: 0, data: {url: "..."}}
      if (data.code === 0 || data.code === 200) {
        if (data.data && typeof data.data === 'object' && data.data.url) {
          if (/^https?:\/\//.test(data.data.url)) return data.data.url;
        }
        if (data.data && typeof data.data === 'string') {
          if (/^https?:\/\//.test(data.data)) return data.data;
        }
        // 直接在根级 url
        if (data.url && /^https?:\/\//.test(data.url)) return data.url;
      }

      // 格式2: {url: "..."}
      if (data.url && /^https?:\/\//.test(data.url)) return data.url;

      // 格式3: 直接在 result/data 中
      if (data.data && typeof data.data === 'object') {
        if (data.data.url && /^https?:\/\//.test(data.data.url)) return data.data.url;
      }
    }

    return '';
  } catch (e) {
    return '';
  }
}

// ============================================================
// CatVod Spider 接口实现
// ============================================================

/**
 * homeContent - 首页分类
 * 返回所有音源的排行榜分类
 */
async function homeContent() {
  var categories = [];
  var sourceKeys = ['wy', 'tx', 'kg', 'kw', 'mg'];
  var sourceNames = {
    wy: '网易音乐',
    tx: '腾讯音乐',
    kg: '酷狗音乐',
    kw: '酷我音乐',
    mg: '咪咕音乐'
  };

  for (var si = 0; si < sourceKeys.length; si++) {
    var src = sourceKeys[si];
    var boards = RANK_BOARDS[src];
    if (boards && boards.length > 0) {
      for (var bi = 0; bi < boards.length; bi++) {
        var board = boards[bi];
        categories.push({
          typeId: src + '_rank_' + board.id,
          typeName: sourceNames[src] + '·' + board.name
        });
      }
    }
  }

  return {
    category: { list: categories },
    list: []
  };
}

/**
 * categoryContent - 分类内容
 */
async function categoryContent(tid, page, filter, extend) {
  try {
    if (!tid || tid.indexOf('_rank_') === -1) {
      return { list: [], pagecount: 0 };
    }

    var parts = tid.split('_rank_');
    var source = parts[0];
    var rankId = parts[1];

    if (!CONFIG.sources[source]) {
      return { list: [], pagecount: 0 };
    }

    var pageNum = parseInt(page) || 1;
    var list = [];

    if (source === 'wy') {
      list = await getNetEaseRankSongs(rankId, pageNum);
    } else if (source === 'tx') {
      list = await getTencentRankSongs(rankId, pageNum);
    } else if (source === 'kg') {
      list = await getKuGouRankSongs(rankId, pageNum);
    } else if (source === 'kw') {
      list = await getKuWoRankSongs(rankId, pageNum);
    } else if (source === 'mg') {
      list = await getMiguRankSongs(rankId, pageNum);
    }

    // 计算页数
    var pagecount = list.length >= 30 ? 5 : (list.length > 0 ? 1 : 0);
    return {
      list: list,
      pagecount: pagecount
    };
  } catch (err) {
    return { list: [], pagecount: 0 };
  }
}

/**
 * searchContent - 搜索
 * 同时从多个音源搜索并合并结果
 */
async function searchContent(tid, keyword, page, filter, extend) {
  try {
    if (!keyword) {
      return { list: [] };
    }

    var pageNum = parseInt(page) || 1;

    // 并行搜索多个音源
    var promises = [
      searchNetEase(keyword, pageNum).catch(function() { return []; }),
      searchTencent(keyword, pageNum).catch(function() { return []; }),
      searchKuGou(keyword, pageNum).catch(function() { return []; }),
      searchKuWo(keyword, pageNum).catch(function() { return []; }),
      searchMigu(keyword, pageNum).catch(function() { return []; })
    ];

    var results = await Promise.all(promises);

    // 合并所有结果
    var allResults = [];
    for (var i = 0; i < results.length; i++) {
      allResults = allResults.concat(results[i] || []);
    }

    // 去重 (基于 source + songmid)
    var seen = {};
    var unique = [];
    for (var j = 0; j < allResults.length; j++) {
      var item = allResults[j];
      var key = item.source + '_' + item.songmid;
      if (!seen[key]) {
        seen[key] = true;
        unique.push(item);
      }
    }

    return { list: unique };
  } catch (err) {
    return { list: [] };
  }
}

/**
 * playerContent - 播放器内容
 * 根据歌曲信息获取播放 URL
 */
async function playerContent(flag, videoUrl, parse) {
  try {
    if (!videoUrl) {
      return { parse: 0, url: '', header: '', click: '' };
    }

    var source, songmid, quality;

    if (typeof videoUrl === 'object' && videoUrl !== null) {
      source = videoUrl.source;
      songmid = videoUrl.songmid;
      quality = videoUrl.quality || '320k';
    } else if (typeof videoUrl === 'string') {
      if (videoUrl.indexOf('http') === 0) {
        return { parse: 0, url: videoUrl, header: '', click: '' };
      }
      return { parse: 0, url: '', header: '', click: '' };
    } else {
      return { parse: 0, url: '', header: '', click: '' };
    }

    if (!source || !songmid) {
      return { parse: 0, url: '', header: '', click: '' };
    }

    var playUrl = await getPlayUrl(source, songmid, quality);

    return {
      parse: 0,
      url: playUrl,
      header: '',
      click: ''
    };
  } catch (err) {
    return { parse: 0, url: '', header: '', click: '' };
  }
}

/**
 * detailContent - 详情内容
 */
async function detailContent(tid, id, extend) {
  try {
    if (typeof id === 'object' && id !== null) {
      return { list: [id] };
    }
    return { list: [] };
  } catch (err) {
    return { list: [] };
  }
}

// ============================================================
// CatVod Spider 导出 (使用 return 语句)
// ============================================================

return {
  homeContent: homeContent,
  categoryContent: categoryContent,
  searchContent: searchContent,
  playerContent: playerContent,
  detailContent: detailContent
};