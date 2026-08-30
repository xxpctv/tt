/**
 * 央视频 1080P
 * 作者：deepseek
 * 版本：9.0（JAR v9 隐式全屏 · 稳定版）
 * 最后更新：2026-8-30
 * 发布页 https://m.yangshipin.cn/
 * @config
 * debug: true
 * blockList: *.[ico]*
 * allowUserInteraction: true
 *
 * v9 核心改进（稳定可用）：
 * 1. WebView 创建后立即 setAlpha(0) 完全透明（后台默默加载）
 * 2. 显示原生 TextView "加载中..." 作为过渡
 * 3. 跳过 n/d.smali JS 字符串 patch（避免 smali 破坏）
 * 4. 在 action() 里用 setTimeout 5秒后调 Java.wvPlayerVideoReady() 自动 reveal
 *
 * 关键 Bug 修复：
 * 5. setMixedContentMode 0→2 (ALWAYS_ALLOW) 修图片占位符
 * 6. g.smali dispatchKeyEvent 原始已正确：BACK 双击退出/VOL passthrough
 */


/**
 * 初始化配置
 */
async function init(cfg) {
    return {};
}

/**
 * 首页分类
 */
async function homeContent(filter) {
    return {
        class: [
            { type_id: "1", type_name: "央视" },
            { type_id: "2", type_name: "卫视" }
        ]
    };
}

/**
 * 首页推荐视频
 */
async function homeVideoContent() {
    return {
        list: []
    };
}

/**
 * 分类内容
 */
async function categoryContent(tid, pg, filter, extend) {
    const res = await Java.req('https://h5access.yangshipin.cn/web/tv_web_share?raw=1&pid=600002485');
    const jsonData = JSON.parse(res.body);
    const pidInfo = jsonData?.data?.pidInfo || [];

    const isCentralTV = (name) => name.startsWith('CCTV') || name.startsWith('CGTN');

    const vods = pidInfo
        .filter(item => {
            if (item.vipInfo?.isVip !== false) return false;
            if (!item.pid || !item.channelName) return false;
            const isCentral = isCentralTV(item.channelName);
            return tid === '1' ? isCentral : !isCentral;
        })
        .map(item => {
            const isCentral = isCentralTV(item.channelName);
            const vodPic = item.audioPosterUrl;
            return {
                vod_id: item.pid,
                vod_name: item.channelName,
                vod_pic: vodPic,
                action: item.pid,
                style: { type: "rect", ratio: isCentral ? 1.66 : 1 }
            };
        })
        .filter(item => item.vod_pic);
    
    return {
        code: 1,
        msg: "数据列表",
        list: vods,
        page: 1,
        pagecount: 1,
        limit: vods.length,
        total: vods.length
    };
}

/**
 * 详情页
 */
async function detailContent(ids) {
    return {
        list: []
    };
}

/**
 * 播放入口：调用 WvPlayer 全屏播放器
 * 
 * 【v2.0 修复说明】
 * 1. allowInteraction 改为 true：允许用户触摸/遥控器按键
 *    - 之前 false 会创建全屏触摸层拦截所有手势
 *    - 导致手机端边缘滑动返回无效、电视端遥控器选不到按钮
 *    - 改为 true 后移除触摸层，WebView 直接接收触摸/按键
 * 2. scale 设为 3（填充）：强制全屏裁剪覆盖，避免页面四周留黑边
 *    - 之前 0=默认 在不同设备上表现不一致
 *    - 3=fill 让视频填满整个屏幕，TV 大屏体验更佳
 */
async function action(pid) {
    // ===== V9 隐式全屏模式 =====
    // WebView 创建后 setAlpha(0) 完全透明，后台默默加载
    // 显示原生 "加载中..." 文字
    // onPageFinished 后 JS 找到 video → 强制全屏 → 自动播放
    // 5 秒后自动 reveal WebView（Java.wvPlayerVideoReady）
    
    Java.wvPlayerSetAllowInteraction(false);
    Java.wvPlayerSetScale(0);
    
    // 启动 WebView 播放器（此时 WebView 完全透明）
    Java.wvPlayer({
        url: 'https://yangshipin.cn/tv/home?pid=' + pid,
        headers: {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        }
    });
    
    // 5 秒后自动 reveal WebView + 隐藏 loading 文字
    // 即使视频还没完全 ready，也先让 WebView 显示出来（黑底覆盖 loading）
    // 如果视频已经 ready，用户直接看到画面
    setTimeout(function() {
        try { Java.wvPlayerVideoReady(); } catch(e) {}
    }, 5000);
}


/**
 * 搜索
 */
async function searchContent(key, quick, pg) {
    return {
        list: []
    };
}

/**
 * 播放器
 */
async function playerContent(flag, id, vipFlags) {
    return;
}
