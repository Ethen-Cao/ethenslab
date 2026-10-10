import re

# 1. Update SKILL.md
with open("work/skills/plantuml/SKILL.md", "r", encoding="utf-8") as f:
    text = f.read()

# Add packageFontColor and rectangle<<ext>> to architecture template
arch_dark = """skinparam component {
    BackgroundColor #34A853
    BorderColor #5F6368
    FontColor #FFFFFF
}
skinparam package {
    BackgroundColor #202124
    BorderColor #5F6368
    FontColor #E8EAED
}"""

arch_dark_new = """skinparam component {
    BackgroundColor #34A853
    BorderColor #5F6368
    FontColor #FFFFFF
}
skinparam packageBackgroundColor #202124
skinparam packageBorderColor #5F6368
skinparam packageFontColor #E8EAED
skinparam package {
    BackgroundColor #202124
    BorderColor #5F6368
    FontColor #E8EAED
}
skinparam rectangle<<ext>> {
    BackgroundColor #3C4043
    FontColor #E8EAED
}
hide stereotype"""

text = text.replace(arch_dark, arch_dark_new)

# Add hide stereotype / participant<<ext>> to sequence template
seq_dark = """    ArrowColor #BDC1C6
    ArrowFontColor #E8EAED
}"""

seq_dark_new = """    ArrowColor #BDC1C6
    ArrowFontColor #E8EAED
}
skinparam participant<<ext>> {
    BackgroundColor #3C4043
    FontColor #E8EAED
}
hide stereotype"""

text = text.replace(seq_dark, seq_dark_new)

# Replace the text explanation in SKILL.md for Sequence diagrams
seq_doc_old = """- 参与者按主要交互顺序从左到右排列，每个参与者含义稳定（进程、线程或服务对象）。本图范围内的参与者用绿色，并用 `box` 圈出范围；范围外的调用方和外部服务用灰色。
- `activate` / `deactivate`"""

seq_doc_new = """- 参与者按主要交互顺序从左到右排列，每个参与者含义稳定（进程、线程或服务对象）。本图范围内的参与者用绿色，并用 `box` 圈出范围；范围外的调用方和外部服务用灰色。
- 为外部参与者（灰色节点）统一使用 `<<ext>>` 版型，并在样式区添加 `hide stereotype`，名称使用 `参与者\\n(角色)` 两行对齐格式。
- `activate` / `deactivate`"""

text = text.replace(seq_doc_old, seq_doc_new)

# Update "亮色版本" description to mention packageFontColor
light_doc_old = """同时修改节点和 `box` 上的显式颜色、外部参与者的文字颜色，以及 `<style>` 中 `root`、`arrow` 的 `LineColor` 与 `FontColor`。只改 `backgroundColor` 会留下浅色文字和边框。"""
light_doc_new = """同时修改节点和 `box` 上的显式颜色、外部参与者的文字颜色、`packageFontColor`，以及 `<style>` 中 `root`、`arrow` 的 `LineColor` 与 `FontColor`。只改 `backgroundColor` 会留下浅色文字和边框。"""

text = text.replace(light_doc_old, light_doc_new)

with open("work/skills/plantuml/SKILL.md", "w", encoding="utf-8") as f:
    f.write(text)


# 2. Update PlantUML 元素规范.md
with open("content/others/PlantUML 元素规范.md", "r", encoding="utf-8") as f:
    text = f.read()

# Apply the same string replacements
text = text.replace(arch_dark, arch_dark_new)
text = text.replace(seq_dark, seq_dark_new)
text = text.replace(light_doc_old, light_doc_new)

# Replace hardcoded participant and rectangle colors in the examples in 元素规范.md
text = text.replace('rectangle "外部执行服务" as Backend #3C4043', 'rectangle "外部执行服务\\n(Backend)" as Backend <<ext>>')
text = text.replace('participant "<color:#E8EAED>调用方</color>" as Caller #3C4043', 'participant "调用方\\n(Caller)" as Caller <<ext>>')
text = text.replace('participant "<color:#E8EAED>外部服务</color>" as External #3C4043', 'participant "外部服务\\n(External)" as External <<ext>>')
# Also remove #202124 from box
text = text.replace('box "任务服务" #202124', 'box "任务服务"')

with open("content/others/PlantUML 元素规范.md", "w", encoding="utf-8") as f:
    f.write(text)


# 3. Update assets/architecture.puml
with open("work/skills/plantuml/assets/architecture.puml", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace(arch_dark, arch_dark_new)
text = text.replace('rectangle "外部执行服务" as Backend #3C4043', 'rectangle "外部执行服务\\n(Backend)" as Backend <<ext>>')

with open("work/skills/plantuml/assets/architecture.puml", "w", encoding="utf-8") as f:
    f.write(text)


# 4. Update assets/sequence.puml
with open("work/skills/plantuml/assets/sequence.puml", "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace(seq_dark, seq_dark_new)
text = text.replace('participant "<color:#E8EAED>调用方</color>" as Caller #3C4043', 'participant "调用方\\n(Caller)" as Caller <<ext>>')
text = text.replace('participant "<color:#E8EAED>外部服务</color>" as External #3C4043', 'participant "外部服务\\n(External)" as External <<ext>>')
text = text.replace('box "任务服务" #202124', 'box "任务服务"')

with open("work/skills/plantuml/assets/sequence.puml", "w", encoding="utf-8") as f:
    f.write(text)

# 5. Update assets/flow.puml (just in case it uses packageFontColor)
with open("work/skills/plantuml/assets/flow.puml", "r", encoding="utf-8") as f:
    text = f.read()

# Flow usually uses partition, let's check
flow_old = """skinparam partition {
  BackgroundColor #202124
  BorderColor #5F6368
  FontColor #E8EAED
}"""

flow_new = """skinparam partition {
  BackgroundColor #202124
  BorderColor #5F6368
  FontColor #E8EAED
}
hide stereotype"""
text = text.replace(flow_old, flow_new)

with open("work/skills/plantuml/assets/flow.puml", "w", encoding="utf-8") as f:
    f.write(text)

print("Upgrade completed")
