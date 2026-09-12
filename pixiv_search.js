/**
 * Pixiv 搜索 PID（浏览器控制台原生 JS）
 * ====================================
 * 用法：
 *   1. 在已登录 pixiv 的标签页打开控制台（F12）
 *      （推荐先打开 https://www.pixiv.net/ 确认已登录）
 *   2. 粘贴本脚本并回车，脚本会 prompt 让你输入搜索标签、数量、页数
 *   3. 脚本调用 https://www.pixiv.net/ajax/search/artworks/<标签> 获取 PID
 *      并在控制台以「每行一个 PID」的格式输出，方便直接复制
 *
 * 说明：
 *   - 搜索接口走同源 fetch（credentials:'include'），必须已登录 pixiv
 */
(function () {
    'use strict';

    // ==================== 参数 ====================
    // 也可直接改下面这 3 个值，避免每次 prompt
    const CONFIG = {
        tag: null,   // 搜索标签（建议日文，如 フリーレン），null 则走 prompt
        count: 30,   // 获取 PID 数量
        pages: 30,    // 搜索页数（每页最多 60）
    };
    // =============================================

    // 从 prompt 读取参数（仅当 CONFIG.tag 为空时）
    function readConfig() {
        if (CONFIG.tag === null) {
            const tag = prompt('请输入搜索标签（建议日文，如 フリーレン）：');
            if (!tag) { console.log('❌ 已取消'); return null; }
            CONFIG.tag = tag;
            const c = prompt(`获取 PID 数量（默认 ${CONFIG.count}）：`) || CONFIG.count;
            CONFIG.count = parseInt(c, 10) || CONFIG.count;
            const p = prompt(`搜索页数，每页最多60（默认 ${CONFIG.pages}）：`) || CONFIG.pages;
            CONFIG.pages = parseInt(p, 10) || CONFIG.pages;
        }
        return CONFIG;
    }

    // 获取 PID 列表
    async function getPidList(tag, count, pages) {
        const ids = [];
        let pn = 1;
        while (ids.length < count && pn <= pages) {
            const url = `https://www.pixiv.net/ajax/search/artworks/${encodeURIComponent(tag)}`
                + `?word=${encodeURIComponent(tag)}&order=date_d&mode=all&s_mode=s_tag&type=all&p=${pn}`;
            try {
                const r = await fetch(url, { credentials: 'include' });
                const j = await r.json();
                const data = (j && j.body && j.body.illustManga && j.body.illustManga.data) || [];
                if (!data.length) { console.log(`⚠️ 第${pn}页无结果，停止`); break; }
                for (const item of data) {
                    if (ids.length >= count) break;
                    ids.push(String(item.id));
                }
                console.log(`📄 第${pn}页: 累积获取 ${ids.length} 个 PID（该页 ${data.length} 个）`);
            } catch (e) {
                console.warn(`⚠️ 第${pn}页请求失败: ${e.message}`);
                break;
            }
            pn++;
            await new Promise(res => setTimeout(res, 300));
        }
        return ids;
    }

    // ==================== 主流程 ====================
    async function main() {
        const cfg = readConfig();
        if (!cfg) return;
        console.log(`🔍 搜索标签: ${cfg.tag}，目标获取 ${cfg.count} 个 PID`);

        const pids = await getPidList(cfg.tag, cfg.count, cfg.pages);
        if (!pids.length) { console.log('❌ 未获取到任何 PID（请确认已登录 pixiv）'); return; }
        console.log(`✅ 获取到 ${pids.length} 个 PID，以下是换行格式（可直接复制）：`);
        console.log('\n' + pids.join('\n') + '\n');

        // 写入剪贴板（如浏览器允许）
        try {
            await navigator.clipboard.writeText(pids.join('\n'));
            console.log('📋 已自动复制到剪贴板');
        } catch (e) {
            console.log('📋 未自动复制（可手动选择上方文本复制）');
        }
    }

    main().catch(e => console.error('❌ 脚本出错:', e));
})();
