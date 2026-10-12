# Local verification

使用实际发现的 draw.io CLI 和现有权限。下面是 Linux draw.io 32.4.1 上已验证的参数；其他版本先看 `--help`，不盲目照搬路径、版本或显示服务器配置。生成 XML 不要求安装桌面端，以下仅用于验收。

## Isolated render and roundtrip

先用 `command -v drawio` 找到可执行文件。创建隔离 QA 目录：

```bash
drawio_qa_dir=$(mktemp -d /tmp/drawio-qa-XXXXXX)
```

下面的变量 `diagram_file` 设置为本次产物的绝对路径；不要把用户 profile 作为测试目录。GUI / Electron 若被沙箱阻止，使用产品提供的授权流程，不更改安装包或安全策略。

```bash
drawio --export --format png --scale 1 --border 24 --theme light \
  --output "$drawio_qa_dir/preview.png" \
  --user-data-dir="$drawio_qa_dir/profile" --disable-update --timeout 45 \
  "$diagram_file"
```

```bash
drawio --export --format xml --uncompressed \
  --output "$drawio_qa_dir/roundtrip.xml" \
  --user-data-dir="$drawio_qa_dir/profile" --disable-update --timeout 45 \
  "$diagram_file"
python scripts/check-drawio.py "$drawio_qa_dir/roundtrip.xml" --model "$model_file"
```

`model_file` 为首轮导出的源模型。维护用户手工调整过的图时省略 `--model`，另审查本次改动的身份与关系。不要拿旧模型的全部坐标覆盖其手工布局。

如需 SVG 预览：

```bash
drawio --export --format svg --border 24 --theme light \
  --embed-svg-fonts true --embed-svg-metadata \
  --output "$drawio_qa_dir/preview.svg" \
  --user-data-dir="$drawio_qa_dir/profile" --disable-update --timeout 45 \
  "$diagram_file"
```

确保新输出确实存在且格式有效；退出码和“导出成功”提示不能代替检查。SVG可能包含 HTML 标签局部 PNG；原生 `.drawio` 没有整图 image 且保持真实 vertices / edges，才说明它不是图片伪装。PNG 是验收截图，不是交付编辑源。

不可用 / 超时先检查可执行文件、显示环境、路径和错误信息。至多做两次有明确修正依据的重试；不要无限启动 Electron、改 Fontconfig 缓存或全局 kill 用户进程。无法渲染时保留源文件并如实报告缺项。

## Visual review

实际打开全图和关键区域；大图按原始尺寸分区查看，不用一个缩小全景截图证明文字可读。

- SoC / VM / Hypervisor / 独立域的边界及对齐仍正确；没有因格式转换把分层变成流程阶段。
- 容器 header 不侵占内容；长名称未截断或缩字；两种字体实际正常，节点副标题未越界。
- 关系端点贴边且末段垂直进入，多个入口有序；标签不遮挡文字 / 线 / 拐点。
- 避免无必要交叉；不可避免交叉为非连接弧，真实分支为点；内存三层可辨且 group 不多出一层边框。

## Movement test

只在临时副本测试。选择有多条边的主链节点，修改其原生 `mxGeometry x/y`，例如 +40 / +16；保持 ID、父级、source / target 不变，且**不运行构建器、不重写折点**。导出前后使用同一 scale、border 和 theme，避免把裁切原点差异误判为连线偏移。

查看实际端点是否随移动而更新、另一端是否保持绑定，标签是否仍归属 edge，并检查新的首尾来向和穿框情况。再抽查跨容器线或容器整体移动。发现问题应调整端口 / 原生折点、重测；不能把已移动的测试副本覆盖交付文件。

实测教训：移动库节点或进程框后，固定 entry / exit 仍绑定，但 `segmentEdgeStyle` 可能从沿目标边界的方向进入端口；节点也可能越出原框。需要在目标外规划足够的末段转角，并调整容器尺寸 / 节点位置，而不是把“绑定保留”报告为完整布局通过。

检查报告区分：源模型校验、原生结构检查、roundtrip、实际视觉审阅和移动测试。结构工具不会证明技术事实，也不会测得实际字体或全局遮挡；每种结果只说明自己覆盖的范围。
