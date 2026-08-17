(async function () {
    // 远程cookie地址
    const cookieUrl = "https://cdn09022024.gitlink.org.cn/api/v1/repos/ajeo/k1/raw/my/.quark_cookie.txt";
    // 保存路径：内部存储 /feimao/.quark_cookie.txt
    const saveDir = "/storage/emulated/0/feimao";
    const savePath = saveDir + "/.quark_cookie.txt";

    try {
        //1. 创建文件夹，不存在就新建
        if (!LocalFile.exists(saveDir)) {
            LocalFile.mkdirs(saveDir);
            toast("已创建feimao文件夹");
        }

        //2. 远程下载文件内容
        let resp = await fetch(cookieUrl);
        if (!resp.ok) throw new Error("网络请求失败:" + resp.status);
        let text = await resp.text();

        //3. 写入本地文件
        LocalFile.write(savePath, text);
        toast("✅ Cookie保存成功！路径：" + savePath);

    } catch (e) {
        toast("❌失败:" + e.message);
        console.log("错误详情", e);
    }
})();
