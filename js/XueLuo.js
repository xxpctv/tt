/**
 * XueLuo Spider for CatVod / OK影视
 * ❄️雪咯音乐 v2.0 - 基于 aidaox-20260825-214819.jar 逆向分析
 * 
 * 可用音源 (经过实测验证):
 *   kw (酷我) - 接受网易数字 songmid, 直接返回音频流 (audio/mpeg)
 *   tx (腾讯) - 接受 QQ 字母数字 songmid, 302 重定向到 CDN (car-er.kuwo.cn)
 *   
 * 已失效音源 (实测返回 403/404/空响应):
 *   kg (酷狗) - PHP 返回 404
 *   wy (网易) - PHP 返回 {"code":403,"msg":"未授权客户端"}
 *   mg (咪咕) - PHP 返回空响应
 * 
 * 搜索 API (公开可用):
 *   网易音乐搜索 - https://music.163.com/api/search/get/web
 *   QQ音乐搜索 - https://c.y.qq.com/soso/fcgi-bin/client_search_cp
 * 
 * 使用方法 (CatVod 配置):
 *   {
 *     "key": "XueLuo-肥猫",
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

const CONFIG = {
  // 搜索 API: 公开可用的音乐搜索接口
  searchApi: {
    // 网易搜索 - 返回数字格式 songmid (如 186858, 5257138)
    // 文档: https://music.163.com/#/discover
    wy: 'https://music.163.com/api/search/get/web',
    // QQ 搜索 - 返回字母数字格式 songmid (如 0039MnYb0qxYhV)
    tx: 'https://c.y.qq.com/soso/fcgi-bin/client_search_cp'
  },

  // 播放 URL API (已通过 Node.js 实测验证)
  musicApi: {
    // 酷我 PHP - 接受网易数字 songmid, 直接返回音频流
    // 响应: 200 OK, Content-Type: audio/mpeg
    kw: 'https://mcp.nianxinxz.com/share/ceshi/kw.php',
    // 腾讯 PHP - 接受 QQ songmid, 302 重定向到 CDN
    // 重定向目标: https://car-er.kuwo.cn/.../trackmedia/M{songmid}.mp3
    tx: 'https://mcp.nianxinxz.com/share/ceshi/tx.php'
  },

  // 音源映射关系 (搜索来源 → 播放 API)
  sourceMap: {
    wy: 'kw',   // 网易搜索结果 → 酷我 PHP 播放
    tx: 'tx'    // QQ 搜索结果 → 腾讯 PHP 播放
  },

  // 音质映射 (CatVod 标识 → PHP level 参数)
  qualityMap: {
    '128k': 'standard',
    '320k': 'exhigh',
    'flac': 'lossless',
    'flac24bit': 'hires'
  },

  // 各音源支持的音质 (基于 SVIP音源.js 解码结果)
  supportedQuality: {
    kw: ['128k', '320k', 'flac'],
    tx: ['128k', '320k', 'flac', 'flac24bit']
  },

  // 默认音质 (320k 音质较好且兼容性高)
  defaultQuality: '320k',

  // 请求配置
  request: {
    timeout: 10000,
    userAgent: 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36'
  }
};

// ============================================================
// 工具函数
// ============================================================

/**
 * 发送 HTTP GET 请求
 * CatVod 环境支持 fetch API, 此处做兼容处理
 * 
 * @param {string} url 请求 URL
 * @param {object} headers 额外请求头
 * @returns {Promise<object|string>} 响应数据
 */
async function httpGet(url, headers) {
  const response = await fetch(url, {
    method: 'GET',
    headers: Object.assign({
      'User-Agent': CONFIG.request.userAgent,
      'Accept': 'application/json, text/plain, */*'
    }, headers || {})
  });

  if (!response.ok && response.status !== 302) {
    throw new Error('HTTP ' + response.status + ': ' + response.statusText);
  }

  // CatVod fetch 返回的对象可能没有 text() 方法
  // 需要兼容处理
  const text = typeof response.text === 'function' 
    ? await response.text() 
    : (response.body || '');

  try {
    return JSON.parse(text);
  } catch (e) {
    return text;
  }
}

/**
 * 安全的字符串转义
 */
function safeStr(str) {
  return (str || '').toString();
}

// ============================================================
// 搜索功能
// ============================================================

/**
 * 网易音乐搜索
 * 
 * API 文档: https://music.163.com/#/discover
 * 返回格式: { result: { songs: [...] } }
 * 每首歌包含: id (songmid), name, artists[], album, duration
 * 
 * @param {string} keyword 搜索关键词
 * @param {number} page 页码 (从1开始)
 * @param {number} limit 每页数量 (最大100)
 * @returns {Array} 标准化的搜索结果
 */
async function searchFromWangyi(keyword, page, limit) {
  page = page || 1;
  limit = limit || 20;

  const url = CONFIG.searchApi.wy 
    + '?s=' + encodeURIComponent(keyword) 
    + '&type=1' 
    + '&offset=' + ((page - 1) * limit) 
    + '&limit=' + limit;

  const data = await httpGet(url, {
    'Referer': 'https://music.163.com/',
    'Origin': 'https://music.163.com'
  });

  const results = [];

  if (data && data.result && Array.isArray(data.result.songs)) {
    for (let i = 0; i < data.result.songs.length; i++) {
      const song = data.result.songs[i];
      const artists = Array.isArray(song.artists) 
        ? song.artists.map(function(a) { return a.name; }).join(', ')
        : safeStr(song.artist);

      results.push({
        // CatVod 标准字段
        title: safeStr(song.name) || '未知歌曲',
        artist: artists || '未知歌手',
        album: safeStr(song.album ? song.album.name : ''),
        duration: song.duration || 0,

        // 音源信息 (playerContent 需要)
        source: 'kw',                    // 使用 kw.php 播放
        searchSource: 'wy',              // 标记来源为网易
        songmid: safeStr(song.id),       // 网易数字 songmid
        rawId: safeStr(song.id),
        picUrl: safeStr(song.album ? song.album.picUrl : ''),
        artistIds: Array.isArray(song.artists) 
          ? song.artists.map(function(a) { return safeStr(a.id); }).join(',')
          : '',
        albumId: safeStr(song.album ? song.album.id : '')
      });
    }
  }

  return results;
}

/**
 * QQ 音乐搜索
 * 
 * 返回格式: callback({ data: { song: { list: [...] } } })
 * 每首歌包含: songmid, songname, singer[], albumname, albummid
 * 
 * @param {string} keyword 搜索关键词
 * @param {number} page 页码 (从1开始)
 * @param {number} limit 每页数量 (最大30)
 * @returns {Array} 标准化的搜索结果
 */
async function searchFromQQ(keyword, page, limit) {
  page = page || 1;
  limit = limit || 20;

  const url = CONFIG.searchApi.tx 
    + '?w=' + encodeURIComponent(keyword) 
    + '&p=' + page 
    + '&n=' + limit;

  const rawData = await httpGet(url, {
    'Referer': 'https://y.qq.com/',
    'Origin': 'https://y.qq.com'
  });

  // QQ 搜索返回 JSONP 格式: callback({...})
  let data = rawData;
  if (typeof rawData === 'string') {
    const match = rawData.match(/callback\((.*)\)/);
    if (match) {
      try {
        data = JSON.parse(match[1]);
      } catch (e) {
        data = rawData;
      }
    }
  }

  const results = [];

  if (data && data.data && data.data.song && Array.isArray(data.data.song.list)) {
    for (let i = 0; i < data.data.song.list.length; i++) {
      const song = data.data.song.list[i];
      const singers = Array.isArray(song.singer)
        ? song.singer.map(function(s) { return s.name; }).join(', ')
        : '';

      results.push({
        title: safeStr(song.songname) || '未知歌曲',
        artist: singers || '未知歌手',
        album: safeStr(song.albumname),
        duration: song.interval || 0,

        source: 'tx',                     // 使用 tx.php 播放
        searchSource: 'tx',               // 标记来源为 QQ
        songmid: safeStr(song.songmid),   // QQ 字母数字 songmid
        rawId: safeStr(song.songmid),
        picUrl: '',
        artistIds: Array.isArray(song.singer)
          ? song.singer.map(function(s) { return safeStr(s.id); }).join(',')
          : '',
        albumId: safeStr(song.albummid)
      });
    }
  }

  return results;
}

// ============================================================
// 播放 URL 获取
// ============================================================

/**
 * 通过 kw.php 获取播放 URL
 * 
 * 酷我 PHP 接口接受网易数字格式 songmid
 * 直接返回音频流 (Content-Type: audio/mpeg)
 * 实测可用 ID: 186858, 5257138, 210049
 * 
 * @param {string} songmid 网易数字 songmid
 * @param {string} quality 音质 (128k/320k/flac)
 * @returns {Promise<string>} 音频 URL
 */
async function getKwPlayUrl(songmid, quality) {
  quality = quality || CONFIG.defaultQuality;
  const level = CONFIG.qualityMap[quality] || 'standard';
  
  // 构建 PHP 请求 URL
  const url = CONFIG.musicApi.kw 
    + '?id=' + encodeURIComponent(songmid) 
    + '&level=' + level 
    + '&type=mp3';

  // 验证 ID 有效性 (网易 songmid 通常是 6-10 位数字)
  if (!songmid || songmid.length < 6) {
    throw new Error('无效的歌曲 ID');
  }

  // kw.php 直接返回音频流，CatVod 可以处理
  // 返回 PHP URL，CatVod 会请求并获取音频
  return url;
}

/**
 * 通过 tx.php 获取播放 URL
 * 
 * 腾讯 PHP 接口接受 QQ 字母数字格式 songmid
 * 返回 302 重定向到真实 CDN URL
 * 实测可用 ID: 0039MnYb0qxYhV, 001Bbywq2gicae
 * 
 * @param {string} songmid QQ songmid (字母数字混合)
 * @param {string} quality 音质 (128k/320k/flac/flac24bit)
 * @returns {Promise<string>} 音频 URL (可能是 CDN 直链)
 */
async function getTxPlayUrl(songmid, quality) {
  quality = quality || CONFIG.defaultQuality;
  const level = CONFIG.qualityMap[quality] || 'standard';
  
  const url = CONFIG.musicApi.tx 
    + '?id=' + encodeURIComponent(songmid) 
    + '&level=' + level 
    + '&type=mp3';

  // 验证 ID 有效性
  if (!songmid || songmid.length < 8) {
    throw new Error('无效的歌曲 ID');
  }

  // 尝试获取最终重定向 URL
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'User-Agent': CONFIG.request.userAgent,
        'Accept': '*/*'
      }
    });

    // 如果 fetch 自动跟随了重定向
    // response.url 应该已经是最终 CDN URL
    if (response.url && response.url !== url && response.url.includes('kuwo.cn')) {
      return response.url;
    }

    // 检查是否有 Location 头
    if (response.headers && response.headers.location) {
      return response.headers.location;
    }

    // 如果响应体是 URL 字符串
    const text = typeof response.text === 'function' 
      ? await response.text() 
      : (response.body || '');
    if (text && typeof text === 'string' && text.startsWith('http')) {
      return text.trim();
    }

    // 默认返回原始 URL (CatVod 可能会自行处理重定向)
    return url;
  } catch (e) {
    // 降级: 返回原始 URL
    return url;
  }
}

// ============================================================
// CatVod Spider 接口实现
// ============================================================

/**
 * 搜索内容 (CatVod 标准接口)
 * 
 * CatVod 会自动调用此方法获取搜索结果
 * 结果中每条记录会作为 videoUrl 传递给 playerContent
 * 
 * @param {number} tid 类型 ID (3=音乐)
 * @param {string} keyword 搜索关键词
 * @param {string} page 页码 (字符串, 需要转为数字)
 * @param {string} filter 过滤器 (音乐源通常不使用)
 * @param {object} extend 扩展参数
 * @returns {Promise<Array>} 搜索结果数组
 */
async function searchContent(tid, keyword, page, filter, extend) {
  try {
    const pageNum = parseInt(page) || 1;
    const limit = 20;

    // 同时从网易和 QQ 搜索
    // 使用 Promise.all 并行搜索以提高速度
    const wyPromise = searchFromWangyi(keyword, pageNum, limit).catch(function() { return []; });
    const txPromise = searchFromQQ(keyword, pageNum, limit).catch(function() { return []; });
    
    const results = await Promise.all([wyPromise, txPromise]);
    const wyResults = results[0];
    const txResults = results[1];

    // 合并结果
    const allResults = wyResults.concat(txResults);

    // 去重 (基于 songmid 或 歌曲名+艺术家)
    const seen = {};
    const unique = [];
    for (let i = 0; i < allResults.length; i++) {
      const item = allResults[i];
      const key = item.songmid || (item.artist + '|' + item.title);
      if (!seen[key]) {
        seen[key] = true;
        unique.push(item);
      }
    }

    return unique;
  } catch (err) {
    // 搜索失败返回空数组
    console.error('[XueLuo] searchContent error: ' + err.message);
    return [];
  }
}

/**
 * 获取播放内容 (CatVod 标准接口)
 * 
 * CatVod 在用户点击歌曲时调用此方法
 * videoUrl 参数就是 searchContent 返回的歌曲对象
 * 
 * @param {string} flag 标记
 * @param {object} videoUrl 歌曲对象 (包含 source, songmid, quality 等)
 * @param {object} parse 解析配置
 * @returns {Promise<object>} 播放信息 { parse, url, header, click }
 */
async function playerContent(flag, videoUrl, parse) {
  try {
    // 验证必要字段
    if (!videoUrl) {
      throw new Error('缺少歌曲信息');
    }

    const source = videoUrl.source;
    const songmid = videoUrl.songmid;

    if (!songmid) {
      throw new Error('缺少歌曲 ID');
    }

    // 获取音质设置
    // CatVod 通常会在 videoUrl 中传递音质信息
    // 默认使用 320k
    let quality = videoUrl.quality || CONFIG.defaultQuality;
    
    // 验证音源支持该音质
    const supported = CONFIG.supportedQuality[source];
    if (supported && supported.indexOf(quality) === -1) {
      // 降级到支持的最高音质
      if (supported.indexOf(CONFIG.defaultQuality) !== -1) {
        quality = CONFIG.defaultQuality;
      } else {
        quality = supported[0];
      }
    }

    // 根据音源获取播放 URL
    let playUrl;
    if (source === 'kw') {
      playUrl = await getKwPlayUrl(songmid, quality);
    } else if (source === 'tx') {
      playUrl = await getTxPlayUrl(songmid, quality);
    } else {
      throw new Error('不支持的音源: ' + source);
    }

    // 返回 CatVod 播放格式
    if (playUrl) {
      return {
        parse: 0,           // 0=直接播放, 1=解析 URL
        url: playUrl,       // 播放 URL
        header: '',         // 附加请求头 (通常为空)
        click: ''           // 点击链接 (通常为空)
      };
    }

    throw new Error('无法获取有效的播放 URL');
  } catch (err) {
    console.error('[XueLuo] playerContent error: ' + err.message);
    // 返回空结果表示播放失败
    return {
      parse: 0,
      url: '',
      header: '',
      click: ''
    };
  }
}

/**
 * 首页内容 (CatVod 标准接口)
 * 
 * 音乐源通常不需要首页
 * 如果需要可以返回推荐歌曲列表
 * 
 * @returns {Promise<Array>} 首页内容
 */
async function homeContent() {
  // 音乐源不需要首页内容
  return [];
}

// ============================================================
// 导出 (CatVod 标准格式)
// ============================================================

module.exports = {
  // CatVod 必需接口
  searchContent: searchContent,
  playerContent: playerContent,
  homeContent: homeContent,

  // 调试工具 (可选导出)
  CONFIG: CONFIG,
  searchFromWangyi: searchFromWangyi,
  searchFromQQ: searchFromQQ,
  getKwPlayUrl: getKwPlayUrl,
  getTxPlayUrl: getTxPlayUrl
};