(function () {
    // ---- 检测页面类型并提取图片 ----
    let urls = [];

    // 类型1: 新版 opus 动态详情页
    const opusContainer = document.querySelector('.opus-module-content.opus-paragraph-children');
    if (opusContainer) {
        console.log('📄 检测到新版 opus 布局');
        opusContainer.querySelectorAll('picture source[type="image/avif"]').forEach(source => {
            const srcset = source.getAttribute('srcset');
            if (srcset) {
                const cleanUrl = srcset.replace(/@.*$/, '');
                if (/\.(jpg|jpeg|png|gif|webp|bmp|svg)$/i.test(cleanUrl)) {
                    urls.push(cleanUrl.startsWith('//') ? 'https:' + cleanUrl : cleanUrl);
                }
            }
        });
    }

    // 类型2: 旧版 read 专栏页
    const readContainer = document.querySelector('#read-article-holder, .article-content');
    if (readContainer && urls.length === 0) {
        console.log('📄 检测到旧版 read 布局');
        readContainer.querySelectorAll('img[data-src], img.normal-img').forEach(img => {
            // 优先用 data-src (懒加载原图)，回退到 src
            let src = img.getAttribute('data-src') || img.getAttribute('src');
            if (src) {
                const cleanUrl = src.replace(/@.*$/, '');
                if (/\.(jpg|jpeg|png|gif|webp|bmp|svg)$/i.test(cleanUrl)) {
                    urls.push(cleanUrl.startsWith('//') ? 'https:' + cleanUrl : cleanUrl);
                }
            }
        });
    }

    // 去重
    urls = [...new Set(urls)];

    if (urls.length === 0) {
        console.log('❌ 未找到任何图片，请确认页面已加载完成');
        return;
    }

    const total = urls.length;
    console.log(`📸 共 ${total} 张图片，开始下载...`);
    urls.forEach((url, i) => console.log(`  ${i + 1}. ${url}`));

    // ---- 逐个下载 ----
    let completed = 0;

    function downloadImage(url) {
        const filename = url.split('/').pop().split('?')[0]; // 取文件名，去掉查询参数

        fetch(url, { mode: 'cors' })
            .then(res => {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.blob();
            })
            .then(blob => {
                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(blobUrl);
                completed++;
                console.log(`✅ (${completed}/${total}) ${filename}`);
                if (completed === total) console.log('🎉 全部下载完成！');
            })
            .catch(err => {
                console.warn(`⚠️ (${completed + 1}/${total}) fetch失败，已在新标签页打开: ${filename}`, err.message);
                window.open(url, '_blank');
                completed++;
                if (completed === total) console.log('🎉 全部已处理（部分需手动保存）！');
            });
    }

    urls.forEach((url, i) => setTimeout(() => downloadImage(url), i * 400));
})();