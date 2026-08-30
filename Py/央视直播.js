/**
 * 央视频 1080P
 * 作者：deepseek
 * 版本：5.0（JAR v5 最终修复版）
 * 最后更新：2026-9-1
 * 发布页 https://m.yangshipin.cn/
 * @config
 * debug: true
 * blockList: *.[ico|png|jpeg|jpg|gif|webp]*
 * allowUserInteraction: true
 *
 * v5 修复内容（JAR smali 补丁）：
 * 【手机端】
 * 1. 双击屏幕退出播放：GestureDetector.onDoubleTap → dismiss() 退出
 * 2. 右滑退出播放：GestureDetector.onFling → 水平右滑 >80px 触发 dismiss
 *    - 触摸层 onTouch 返回 true（阻止系统边缘手势退出APP）
 *    - 上下滑动调节音量功能保留（原始逻辑未修改）
 * 【TV端】
 * 3. BACK 键单击退出播放（不再需要双击）
 * 4. 音量键调音量：KEYCODE_VOLUME_UP/DOWN/MUTE → passthrough 给系统
 * 5. D-pad 方向键：全部 forward 给 WebView 并 consume
 *    - WebView 焦点处理由 FrameLayout.dispatchKeyEvent 控制
 * 【通用】
 * 6. 方向切换方法真实实现：wvPlayerIsLandscape/SetLandscape/ToggleOrientation
 * 7. scale 0=默认（按比例适配不裁剪）
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
