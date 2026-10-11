# Publishing to ethenslab

仅在用户要求发布图或更新文章时读取本文件。生成新图不自动授权替换已发布图、原文或历史参考快照。

## Paths

- HTML 落盘于 `static/diagrams/<name>.html`，发布地址 `/ethenslab/diagrams/<name>.html`。
- 模型作为可维护源文件保存在任务约定的位置；生成 HTML 是自包含交付物，不依赖 skill 安装路径或远端 CDN。
- `docs/` 是 Hugo 构建产物，不手工修改。
- 文章 iframe 和备用链接使用相对路径。`../` 数量等于文章 URL 在 `/ethenslab/` 后的层数；存在自定义 URL 时以实际 URL 为准，不只数源文件目录。
- 例如 `content/gunyah/foo.md` 的通常 URL 是 `/ethenslab/gunyah/foo/`，引用 `../../diagrams/<name>.html`；`content/android-dev/media/foo.md` 通常引用 `../../../diagrams/<name>.html`。发布 URL 不包含 `static/`。

## Embed

iframe 的 `title` 使用英文。图外中文备用链接可以保留。先查看生成 HTML 是否提供高度消息协议；不存在时采用足够高度或允许滚动，不添加没有发送端的监听器。

若发送端使用 `{type: '<DIAGRAM_ID>-height', height}`，接收端必须验证消息窗口与 origin：

```html
<iframe id="<DIAGRAM_ID>" src="../../diagrams/<name>.html" title="<English diagram title>" loading="lazy" style="display:block;box-sizing:border-box;width:100%;height:900px;border:1px solid #dadce0;border-radius:8px;"></iframe>
<script>
(() => {
  const frame = document.getElementById('<DIAGRAM_ID>');
  const origin = new URL(frame.src, document.baseURI).origin;
  window.addEventListener('message', event => {
    if (event.source !== frame.contentWindow || event.origin !== origin || event.data?.type !== '<DIAGRAM_ID>-height') return;
    const height = Number(event.data.height);
    if (Number.isFinite(height) && height > 0 && height <= 12000) {
      frame.style.height = `${Math.ceil(height) + 2}px`;
    }
  });
})();
</script>

[独立打开架构图](../../diagrams/<name>.html)
```

上面高度仅为示例。不能设置会裁掉主图的固定高度上限后再隐藏溢出。嵌入后检查实际文章视口、完整显示、相对路径和独立打开链接；不能仅验证独立 HTML。
