# downloadIMG — Pixiv 角色图片自动下载工具

按角色中文名自动完成「取名 → 搜索 PID → 下载图片」的整套流程，基于 Playwright 模拟浏览器 + i.muxmus.com 镜像下载。

> 完整使用说明见 [使用说明.txt](使用说明.txt)

## 主要脚本

| 文件 | 作用 |
| --- | --- |
| `auto_download.py` | 主程序：全自动流程 + 断点续传（推荐） |
| `one_click_character.py` | 一键流程：输入角色名直接下载到目标目录 |
| `muxmus_download.py` | 下载器：按 PID 列表经 i.muxmus.com 并发下载 |
| `pixiv_search.js` | Playwright 注入脚本：pixiv 搜索取 PID |
| `dbiliimg.js` | 备用图片源脚本 |
| `migrate_names.py` | 迁移工具：把散落的 `角色名.txt` 收进 `names/` |
| `cleanup_duplicates.py` | 清理工具：删除与参考目录同名的图片 |

## 数据目录

- `names/` — 每个角色一个 `中文名.txt`，存放已收集的 PID 列表（受版本控制）
- `browser_profile/` — 浏览器登录态缓存（已 gitignore，不提交）
- `pixiv_muxmus/` — 默认图片输出目录（已 gitignore，不提交）

## 环境要求

- Python 3.10+：`requests`
- Node.js：Playwright（Chromium/Edge）
