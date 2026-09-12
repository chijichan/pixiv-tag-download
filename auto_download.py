# -*- coding: utf-8 -*-
"""
一键角色图片自动下载（Playwright 模拟浏览器版）
================================================
输入: 角色中文名 + 下载数量（日文名自动从萌娘百科获取，可确认/修正）
流程:
  1. 输入中文名，自动抓取萌娘百科获取 日文名 + 英文名（失败可手动输入）
  2. 启动 Edge（Playwright 持久化配置，首次需在窗口里手动登录 pixiv，之后免登录）
  3. 用日文名查询 pixiv 作品数，少于 600 自动改用英文名再查；两者都少则警告
  4. 调用 pixiv 搜索接口，获取 N 个作品的 PID
  5. PID 写入 names/<中文名>.txt（自动创建 names/，已有则去重合并）
  6. 调用 muxmus_download.py 经 i.muxmus.com 下载图片到 W:\\临时文件夹\\<中文名>

用法:
    python auto_download.py                # 完整流程：自动取名 + 搜索 + 下载
    python auto_download.py <中文名>       # 断点续传：只补下载缺失图片（跳过浏览器）
"""
import os
import re
import sys
import time
import subprocess
import urllib.parse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("[X] 缺少 playwright，请先安装: pip install playwright")

try:
    import requests
except ImportError:
    sys.exit("[X] 缺少 requests，请先安装: pip install requests")

# ==================== 配置区 ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NAMES_DIR = os.path.join(SCRIPT_DIR, "names")       # 角色名.txt 存放文件夹
PROFILE_DIR = os.path.join(SCRIPT_DIR, "browser_profile")  # 浏览器登录态（持久化）
TARGET_ROOT = r"W:\临时文件夹"                       # 图片下载根目录
DEFAULT_COUNT = 30                                  # 默认下载数量
RETRY = 5                                           # 图片下载网络失败重试次数
MOEGIR_BASE = "https://mzh.moegirl.org.cn/"         # 萌娘百科（自动获取日文名/英文名）
TOO_FEW = 600                                       # pixiv 作品数低于此值视为「太少」
MOEGIR_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
PID_RE = re.compile(r"^\d{5,}$")
LATIN_OK = re.compile(r"^[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F .'\-]*$")
JP_SPAN = re.compile(r'<span lang="ja">([^<]+)</span>')
# ==============================================


def ask_int(prompt, default):
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        print(f"[提示] 输入无效，使用默认 {default}")
        return default


def load_pid_file(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def save_pid_file(path, pids):
    seen, out = set(), []
    for p in pids:
        if p not in seen:
            seen.add(p)
            out.append(p)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + ("\n" if out else ""))


def fetch_moegirl(cn_name):
    """抓取萌娘百科页面，提取角色的 日文名 与 英文名。
    返回 (日文名, 英文名)；英文名可能为空字符串；整体失败返回 ("", "")。
    提取三级锚点：
      1. <span>本名</span> 标签后的名字块（蔚蓝档案等角色卡通用）
      2. <br>(英文名) 块（窗口取上一个 </div> 边界之后，避免混入其他行）
      3. 页面最前面两个 lang=ja 片段（兜底）
    注音假名(rt)块已剔除，不会把读音拼进名字。"""
    url = MOEGIR_BASE + urllib.parse.quote(cn_name)
    html = None
    for i in range(3):  # 萌娘百科偶发超时，重试 3 次
        try:
            r = requests.get(url, headers={"User-Agent": MOEGIR_UA}, timeout=30)
            if r.status_code == 200:
                html = r.text
                break
        except Exception:
            pass
        time.sleep(1.5 * (i + 1))
    if not html:
        return "", ""

    html2 = re.sub(r"<rt\b[^>]*>.*?</rt>", "", html, flags=re.S)

    def take_en(block):
        em = re.search(r"<br[^>]*>\s*\(([^<>()]{2,60})\)", block)
        if em and LATIN_OK.match(em.group(1)):
            return em.group(1).strip()
        return ""

    # 锚点1: <span>本名</span> 后的名字块
    for m in re.finditer(r"<span>\s*本名\s*</span>", html2):
        block = html2[m.end():m.end() + 600]
        jp = "".join(JP_SPAN.findall(block)).strip()
        if jp:
            return jp, take_en(block)

    # 锚点2: <br>(英文名) 块
    for em in re.finditer(r"<br[^>]*>\s*\(([^<>()]{2,60})\)", html2):
        if not LATIN_OK.match(em.group(1)):
            continue
        start = html2.rfind("</div>", 0, em.start())
        window = html2[max(0, start):em.start()]
        jp = "".join(JP_SPAN.findall(window)).strip()
        if jp:
            return jp, em.group(1).strip()

    # 锚点3: 页面最前面两个 ja 片段（兜底）
    spans = JP_SPAN.findall(html2)
    if spans:
        return "".join(spans[:2]).strip(), ""
    return "", ""


def is_logged_in(page):
    """通过调用搜索接口判断是否已登录 pixiv（登录后才能搜）。
    fetch 自带 10 秒超时，避免页面卡住时无限等待。"""
    return page.evaluate("""async () => {
        const withTimeout = (p, ms) => Promise.race([
            p, new Promise(res => setTimeout(() => res(null), ms))
        ]);
        try {
            const r = await withTimeout(fetch(
                '/ajax/search/artworks/%E3%83%86%E3%82%B9%E3%83%88'
                + '?word=%E3%83%86%E3%82%B9%E3%83%88&order=date_d&mode=all&p=1',
                {credentials:'include'}), 10000);
            if (!r) return false;
            const j = await r.json();
            return !!(j && j.body && Array.isArray(j.body.illustManga && j.body.illustManga.data));
        } catch (e) { return false; }
    }""")


def open_pixiv(page):
    """打开 pixiv 首页，等待页面加载稳定（networkidle 超时则忽略，继续）"""
    page.goto("https://www.pixiv.net/", wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass  # pixiv 首页会持续加载资源，networkidle 超时属正常，忽略
    page.wait_for_timeout(1000)


def detect_login(page, attempts=8, delay=1.0):
    """检测登录态：若页面正在跳转导致 evaluate 报错（Execution context was
    destroyed），自动等待并重试，直到页面稳定。返回 True/False；多次失败返回 None"""
    last = None
    for _ in range(attempts):
        try:
            return is_logged_in(page)
        except Exception as e:
            last = e
            time.sleep(delay)
    print(f"[提示] 页面持续跳转，登录态检测未稳定（{last}）")
    return None


def search_total(page, name, s_mode="s_tag"):
    """查询 pixiv 搜索该名字的作品总数。返回总数；-1 表示查询失败（跳过校验）"""
    return page.evaluate("""async ({name, s_mode}) => {
        const withTimeout = (p, ms) => Promise.race([
            p, new Promise(res => setTimeout(() => res(null), ms))
        ]);
        try {
            const r = await withTimeout(fetch(
                `https://www.pixiv.net/ajax/search/artworks/${encodeURIComponent(name)}`
                + `?word=${encodeURIComponent(name)}&order=date_d&mode=all&s_mode=${s_mode}&type=all&p=1`,
                {credentials:'include'}), 15000);
            if (!r) return -1;
            const j = await r.json();
            const t = j && j.body && j.body.illustManga && j.body.illustManga.total;
            return typeof t === 'number' ? t : -1;
        } catch (e) { return -1; }
    }""", {"name": name, "s_mode": s_mode})


def fetch_pids(page, tag, count, s_mode="s_tag"):
    """在已登录的页面上调用 pixiv 搜索接口，按时间倒序获取 count 个 PID。
    每页 fetch 带 20 秒超时，超时自动重试该页（最多 3 次）。"""
    return page.evaluate("""async ({tag, count, s_mode}) => {
        const withTimeout = (p, ms) => Promise.race([
            p, new Promise(res => setTimeout(() => res(null), ms))
        ]);
        const ids = [];
        let pn = 1;
        while (ids.length < count && pn <= 50) {
            const url = `https://www.pixiv.net/ajax/search/artworks/${encodeURIComponent(tag)}`
                + `?word=${encodeURIComponent(tag)}&order=date_d&mode=all&s_mode=${s_mode}&type=all&p=${pn}`;
            let data = null;
            for (let attempt = 0; attempt < 3 && data === null; attempt++) {
                try {
                    const r = await withTimeout(fetch(url, {credentials:'include'}), 20000);
                    if (!r) continue;                     // 超时，重试该页
                    const j = await r.json();
                    data = (j && j.body && j.body.illustManga && j.body.illustManga.data) || [];
                } catch (e) { data = []; break; }         // 网络异常，停止
            }
            if (!data || !data.length) break;             // 3次超时或无结果
            for (const item of data) {
                if (ids.length >= count) break;
                ids.push(String(item.id));
            }
            pn++;
            await new Promise(res => setTimeout(res, 250));
        }
        return ids;
    }""", {"tag": tag, "count": count, "s_mode": s_mode})


def download_images(txt_path, cn):
    """用 PID 列表下载图片到 W:\\临时文件夹\\<中文名>。
    已下载的自动跳过、损坏的自动修复、网络失败重试 RETRY 次——断点续传的核心。"""
    target_dir = os.path.join(TARGET_ROOT, cn)
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n>>> 开始下载 -> {target_dir} ...")
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "muxmus_download.py"),
        txt_path,
        "-o", target_dir,
        "--retry", str(RETRY),
    ]
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"[X] 下载脚本返回码 {rc}")
        return False
    print(f"\n[OK] 全部完成！")
    print(f"      图片目录: {target_dir}")
    print(f"      PID 列表: {txt_path}")
    print(f"      续传命令: python auto_download.py {cn}")
    return True


def main():
    argv = sys.argv[1:]

    # ========== 断点续传模式: python auto_download.py <中文名> ==========
    # 跳过浏览器/搜索，直接用 names/<中文名>.txt 补下载缺失图片
    if argv:
        resume_cn = argv[0].strip()
        txt_path = os.path.join(NAMES_DIR, resume_cn + ".txt")
        if not os.path.exists(txt_path):
            print(f"[X] 找不到 {txt_path}，无法续传（请先正常跑一次完整流程生成该文件）")
            return
        print("=" * 56)
        print("  断点续传模式（跳过浏览器，只补下载缺失图片）")
        print("=" * 56)
        print(f"[OK] 使用已有 PID 列表: {txt_path}（共 {len(load_pid_file(txt_path))} 个）")
        download_images(txt_path, resume_cn)
        return

    print("=" * 56)
    print("  一键角色图片自动下载（模拟浏览器）")
    print("=" * 56)
    cn = input("角色中文名（如 桐藤渚）: ").strip()
    if not cn:
        print("[X] 中文名不能为空")
        return
    count = ask_int(f"下载图片数量（默认 {DEFAULT_COUNT}）: ", DEFAULT_COUNT)

    os.makedirs(NAMES_DIR, exist_ok=True)

    # ---------- 1. 萌娘百科自动获取 日文名/英文名 ----------
    print(f"\n[1/4] 正在查询萌娘百科「{cn}」...")
    jp_name, en_name = fetch_moegirl(cn)
    if jp_name:
        en_txt = f"，英文名「{en_name}」" if en_name else "（页面无英文名）"
        print(f"[OK] 自动获取: 日文名「{jp_name}」{en_txt}")
        fix = input(f"     确认日文名（回车用「{jp_name}」，或输入修正值）: ").strip()
        if fix:
            jp_name = fix
    else:
        print("[提示] 萌娘百科未获取到日文名（页面不存在或格式特殊）")
        jp_name = input("     请手动输入日文名（直接回车取消）: ").strip()
        if not jp_name:
            print("[X] 未提供日文名")
            return
        en_name = ""

    # ---------- 2. 启动浏览器（持久化登录态） ----------
    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                channel="msedge",          # 优先用系统已装的 Edge
                headless=False,
                viewport={"width": 1280, "height": 900},
            )
        except Exception as e:
            print(f"[提示] Edge 启动失败（{e}），回退到 Playwright Chromium ...")
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False,
            )
        page = ctx.new_page()
        try:
            open_pixiv(page)
        except Exception as e:
            print(f"[X] 无法打开 pixiv.net（{e}）")
            print("    请确认系统代理已开启（访问 pixiv 需要代理/VPN），然后重试")
            ctx.close()
            return

        # ---------- 2. 登录态检测（等待页面稳定 + 自动重试） ----------
        logged = detect_login(page)
        if logged is None:
            logged = False

        if not logged:
            print("\n[!] 未检测到 pixiv 登录态。请在打开的浏览器窗口中登录 pixiv，")
            input("    登录完成后回到本程序按回车继续...")
            logged = detect_login(page)
            if not logged:
                try:
                    open_pixiv(page)   # 回到首页再确认一次登录态
                except Exception:
                    pass
                logged = detect_login(page)

        if not logged:
            print("[X] 仍未检测到登录态，请确认已登录 pixiv 后再试")
            ctx.close()
            return

        # ---------- 3. 作品数校验 + 选择搜索词 ----------
        print("[2/4] 校验 pixiv 作品数...")
        total_jp = search_total(page, jp_name, "s_tag")
        total_en = 0
        if total_jp >= 0:
            if total_jp < TOO_FEW and en_name:
                total_en = search_total(page, en_name, "s_tc")
            line = f"[信息] pixiv 作品数: 「{jp_name}」= {total_jp}"
            if en_name:
                line += f"，「{en_name}」= {total_en}"
            print(line)
            if total_jp >= TOO_FEW or total_jp >= total_en:
                search_name, search_mode = jp_name, "s_tag"
            else:
                search_name, search_mode = en_name, "s_tc"
                print(f"[提示] 日文名作品数({total_jp})不足 {TOO_FEW}，改用英文名「{en_name}」({total_en})")
            if max(total_jp, total_en) < TOO_FEW:
                print(f"[警告] 作品数过少，日文名可能不正确，或该角色在 pixiv 作品很少")
                if input("       仍然继续？(y/N): ").strip().lower() != "y":
                    ctx.close()
                    return
        else:
            print("[提示] 作品数查询失败，跳过校验，直接使用日文名")
            search_name, search_mode = jp_name, "s_tag"

        # ---------- 4. 搜索获取 PID ----------
        print(f"[3/4] 搜索「{search_name}」，目标 {count} 个 PID ...")
        pids = fetch_pids(page, search_name, count, search_mode)
        ctx.close()

    if not pids:
        print("[X] 未获取到任何 PID（可能标签无结果，或需要更换搜索词）")
        return

    # ---------- 5. 合并写入 names/<中文名>.txt ----------
    print("[4/4] 写入 PID 列表并下载 ...")
    txt_path = os.path.join(NAMES_DIR, cn + ".txt")
    old = load_pid_file(txt_path)
    old_set = set(old)
    merged = old + [x for x in pids if x not in old_set]
    save_pid_file(txt_path, merged)
    print(f"[OK] PID 已写入 {txt_path}（新 {len(pids)} 个，累计 {len(merged)} 个）")

    # ---------- 6. 下载图片（已存在跳过/损坏修复/断网重试5次） ----------
    if not download_images(txt_path, cn):
        return


if __name__ == "__main__":
    main()
