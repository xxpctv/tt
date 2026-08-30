/**
 * 央视频 1080P
 * 作者：deepseek
 * 版本：6.0（JAR v6 全屏播放版）
 * 最后更新：2026-8-30
 * 发布页 https://m.yangshipin.cn/
 * @config
 * debug: true
 * blockList: *.[ico|png|jpeg|jpg|gif|webp]*
 * allowUserInteraction: true
 *
 * v6 修复内容（JAR smali 补丁）：
 * 【关键 Bug 修复】
 * 1. 图片占位符：setMixedContentMode 0→2 (ALWAYS_ALLOW)
 *    - HTTPS 页面加载 HTTP 图片之前被系统拦截
 * 2. 所有方向都退出：onFling deltaY 加 Math.abs()
 *    - 之前 deltaY 负数(上滑)导致水平判断永远通过
 * 【手机端手势】
 * 3. 双击屏幕退出播放：onDoubleTap → dismiss()
 * 4. 右滑退出播放：onFling → 水平右滑 >80px 触发 dismiss
 *    - 触摸层 return true 阻止系统边缘手势退出APP
 *    - 上下滑调音量功能保留（原始逻辑未修改）
 * 【TV端遥控器】
 * 5. BACK 键单击退出播放
 * 6. 音量键 passthrough 给系统调音量
 * 7. D-pad 方向键 forward WebView + consume
 * 【全屏播放模式】
 * 8. onPageFinished 注入 JS：隐藏页面、强制视频全屏、自动播放
 * 9. 央视网页自带 loading 动画作为过渡（修 mixed content 后正常显示）
 * 10. scale 0=默认（按比例适配不裁剪）
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
    // ===== 关键：禁用触摸拦截层 =====
    // false = 创建透明触摸层，GestureDetector 检测双击返回；
    //         onTouch 返回 false 让滑动事件穿透到 WebView（手机左滑返回）
    // true  = 无触摸层，WebView 直接接收（无法双击返回）
    Java.wvPlayerSetAllowInteraction(false);
    
    // ===== 画面比例：0=默认（按比例适配全屏，不裁剪）=====
    // 可选值: 0=默认(推荐), 1=16:9, 2=4:3, 3=填充(裁剪), 4=原始
    Java.wvPlayerSetScale(0);
    
    // ===== 启动全屏 WebView 播放器 =====
    Java.wvPlayer({
        url: 'https://yangshipin.cn/tv/home?pid=' + pid,
        headers: {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        }
    });
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
