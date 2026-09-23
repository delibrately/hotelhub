# 白车轴度假官网

本地入口：`/stay/`。现有酒店管理系统及其登录、权限和订单流程保持原路由。四个独立房型详情在 `/stay/rooms/<slug>/`。

启动：`.venv/bin/python manage.py runserver 127.0.0.1:8000`

## 文案与图片维护

- 房型数据：`main/retreat.py`。集中管理文案、早餐、卫浴、床型和图片列表。
- 首页：`main/templates/retreat/home.html`。
- 共用导航、咨询弹窗和页脚：`main/templates/retreat/base.html`。
- 图片：`main/static/retreat/images/`。保持文件名替换高清照片即可，也可修改房型数据中的路径。
- 样式与交互：`main/static/retreat/site.css`、`site.js`。

当前 11 张图片由用户授权，从已打开的美篇《导航+价格表+房型介绍》（作者：白车轴·度假）通过微信大图保存，HEIC 转 JPEG 用于网页兼容，没有生成替代场景。图片来源口令：`#小程序://美篇/y2amCkdZLip6Kow`。提取日期：2026-09-23。当前图为美篇版本，后续换高清原片。

| 图片 | 内容 |
| --- | --- |
| forest-cabin.jpg | 林间宿白帘、浴缸及露台，首页主视觉 |
| forest-interior.jpg | 林间宿玻璃屋顶卧室 |
| terrace.jpg | 林间露台休闲椅 |
| hillside-terrace.jpg | 半山度假屋露台 |
| sunshine-cabin.jpg | 阳光房外观 |
| meadow-tents.jpg | 草地帐篷全景 |
| tents-evening.jpg | 帐篷夜景 |
| valley-pool.jpg | 山谷泳池 |
| creek-days.jpg | 溪流亲子场景 |
| garden-table.jpg | 林间天幕餐桌 |
| arrival-stone.jpg | 白车轴入口石标 |

## 预订与上线内容

使用原文公开的预订微信 13039190891、电话 13044350891。仅发起咨询，不创建订单或承诺库存。展示房型配置及入住说明；价格、维护费归属、取消条款及活动开放情况留待预订确认。未伪造地图坐标、二维码、评价或备案号。

本轮仅本地制作与预览，没有部署。正式上线前确认实时经营信息、完整地址和域名/备案等实际资料。

## 本轮验证

- Django 系统检查通过；原项目 139 项测试全部通过。
- 首页与四个房型详情 HTTP 200，不存在的房型返回 404；管理页依然要求登录。
- 浏览器实测桌面与 390px 手机视口；手机页面无横向溢出。
- 已验证菜单开关与锚点、房型跳转、咨询房型上下文、微信号复制、图库切换与关闭、常见问题展开。
- 预览截图：`screenshots/retreat/desktop-home.png`、`screenshots/retreat/mobile-home.png`。

## GitHub Pages

源码分支：`codex/retreat-website`。静态发布分支：`gh-pages`。
站点地址：`https://delibrately.github.io/hotelhub/`。

导出命令：`.venv/bin/python scripts/export_retreat.py --base /hotelhub/`

导出仅包含首页、四个房型页和 `main/static/retreat` 资源；不会导出酒店管理后台、数据库、账号、订单或环境配置。静态站点的咨询、复制微信号、电话链接及图库交互仍可使用。修改源模板或素材后，需要重新导出并更新发布分支。

## White clover 品牌标志

2026-09-23：英文名称统一为 `White clover`，导航与页脚加入用户提供的 logo。采用暖纸色背景，透明图案直接融入页面；移动端缩小标志并保留品牌文字。

- 原始文件：`main/static/retreat/brand/white-clover-logo.png`，保留原图。
- 透明版本：`main/static/retreat/brand/white-clover-transparent.png`，1378 × 1141 RGBA PNG。
- 处理方式：内置 imagegen 图片编辑。去除外围白底、保留三顶帐篷的白色；页面通过 CSS 隐藏图片外围空白。
- 验证：背景 alpha 为 0，帐篷白色保留；手机与桌面布局已截图检查。
- 截图：`screenshots/retreat/mobile-logo.png`、`screenshots/retreat/desktop-logo.png`。

最终图像编辑提示词：

```text
Use case: background-extraction. Edit target: the provided original White clover 白车轴 logo. Remove ONLY the white exterior background and the white background within letter counters; output true transparent PNG alpha, not a checkerboard image. CRITICAL: preserve all THREE WHITE TENTS INSIDE THE NAVY MOUNTAINS, their white fabric must remain opaque white. Preserve original navy mountains, curved baseline, yellow moon and four yellow stars, exact text 'White clover' and '白 车 轴', all shapes, typography, proportions, colors and layout. No redesign, no added text, no shadows, no outline. Crop excessive empty canvas to the entire logo bounding box with small transparent padding, including all lettering. Result must be an exact clean background removal asset for a website.
```
