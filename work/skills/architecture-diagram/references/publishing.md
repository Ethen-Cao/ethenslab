# Publishing to ethenslab

在将图嵌入文章或按用户要求发布到本站时读取本文件。生成新图不自动授权替换已发布图、原文或历史参考快照。

## Delivery context and paths

先确认文章实际 URL、内容栏可用宽度、需要支持的视口，以及图在文章中的作用。浏览器宽度不能代替 iframe 的实际内容宽度；宽栏文章、普通正文栏和移动端应按各自得到的空间验收。优先从现有页面测量，尚无页面时明确记录假设，嵌入后复核。

- HTML 落盘于 `static/diagrams/<name>.html`，发布地址 `/ethenslab/diagrams/<name>.html`。
- 模型作为可维护源文件保存在任务约定的位置。文章使用 `article` 构建模式；需要原始尺寸详图时可另建 `original` 产物，不能直接把宽大原图嵌入后当作文章验收完成。
- 生成 HTML 自包含，不依赖 skill 安装路径或远端 CDN。父文章使用的公共高度适配脚本从 `assets/embed.js` 复制到站点可发布位置，例如 `static/diagrams/embed.js`；同页只加载一次，优先由已有模板统一加载。
- `docs/` 是 Hugo 构建产物，不手工修改。
- iframe、适配脚本和备用链接使用与实际文章 URL 对应的相对路径。`../` 数量等于文章 URL 在 `/ethenslab/` 后的层数；存在自定义 URL 时以实际 URL 为准，不只数源文件目录。
- 例如 `content/gunyah/foo.md` 的通常 URL 是 `/ethenslab/gunyah/foo/`，引用 `../../diagrams/<name>.html`；`content/android-dev/media/foo.md` 通常引用 `../../../diagrams/<name>.html`。发布 URL 不包含 `static/`。

## Build for the article

```bash
node scripts/build-diagram.mjs /absolute/path/input.diagram.json /absolute/path/article.html --presentation article
```

`article` 保持模型的逻辑字号，由公共展示层按宽度适配且不放大。节点主名称实际显示至少 18 CSS px，其他文字至少 14 CSS px，统一取自 `theme.presentation.minNodeFontSize` / `minTextFontSize`。不要在文章中再用 `transform` 或 `zoom` 缩一遍，也不要通过降低逻辑字号、隐藏溢出或加横向滚动让文字阈值检查“通过”。

尺寸由内容决定，文章可以正常纵向滚动，不要求任意架构一屏展示。若目标宽度下字太小，重排层内组件、减少非必要展开，或拆成文章可读总览与独立详图；不能只把详图链接放在不可读缩略图下方就宣称完成。移动宽度不合格时明确记录失败，或为该宽度提供同样通过字号和几何检查的总览。

## Embed with the shared adapter

iframe 用 `data-architecture-diagram="<MODEL_META_ID>"` 标记，值必须与生成图的 `model.meta.id` 一致，`title` 使用英文。下面的初始高度只是在首次高度通知到达前保留空间，最终高度由公共适配器设置；不为不同文章复制消息监听器。

```html
<figure>
  <iframe
    data-architecture-diagram="<MODEL_META_ID>"
    src="../../diagrams/<name>.html"
    title="<English diagram title>"
    loading="lazy"
    style="display:block;box-sizing:border-box;width:100%;height:640px;border:1px solid #dadce0;border-radius:8px;">
  </iframe>
  <figcaption><a href="../../diagrams/<name>.html" target="_blank" rel="noopener">独立打开架构图</a></figcaption>
</figure>
<script src="../../diagrams/embed.js" defer></script>
```

`assets/embed.js` 服务同源嵌入：核对 `event.source`、`event.origin` 和消息 `type`。图发送 `{type: "<MODEL_META_ID>-height", height}`，高度必须为有限 number 且位于 `(0, 12000]`；父页面通过 `<MODEL_META_ID>-request-height` 请求当前高度，因此晚加载适配脚本也能获得回应。统一复用这份适配器，不逐篇复制监听代码。独立打开 HTML 不要求父页面或外部脚本存在。

确认适配脚本确实随站点发布，发送端在初次渲染和可用宽度变化后能更新高度。高度超出协议范围时应重排、拆图或报告失败，不能把拒绝同步的状态当作通过。不能设置会裁掉图的固定高度上限再隐藏溢出；也不能把 iframe 内部滚动条误认成文章页面的正常纵向滚动。若 CSP、加载错误或不同源导致适配器未工作，应修复或明确报告嵌入未通过，不能仅因原图能打开就给出成功结论。

## Verify the embedding and the real page

先对实际作者生成的文章 HTML 做嵌入 fixture 验证。`--widths` 指定实际 iframe 外宽，报告中还应记录扣除边框后的内容宽度；下面数值是示例，不是全站固定宽度或必过宽度。

```bash
node scripts/verify-article.mjs --input /absolute/path/article.html --output /tmp/article-qa --widths 1200,960 --browser /path/to/chromium
```

需要支持移动端时，将实际移动宽度纳入独立运行或该列表；不能只报告桌面通过。检查每个宽度的实际字号、横向溢出、裁切、内部滚动、高度通知和视口截图。full-page 截图可以补充完整图形检查，不能替代读者视口中的截图，也不能通过扩大测试视口来适配原始画布。

fixture 只能验证模拟的嵌入环境。还要打开真实预览或发布页面，核对实际 iframe 内容宽度、父容器样式、相对路径、脚本加载、图文衔接与独立打开链接；需要时在允许的浏览器环境中手工检查。不把 fixture 通过写成真实站点已验证，不把截图成功保存写成已经目视检查。

验收记录至少包含图的源模型和生成 HTML、模式、文章 URL、可用宽度与浏览器视口、各宽度的结果、视口截图位置，以及真实页面是否已检查。回归记录模板与实际作者图的选取见 [schema.md](schema.md#regression-cases-from-authored-diagrams)。
