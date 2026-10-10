import re

with open("content/qnx/qnx-screen-graphics-subsystem.md", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Base style replacement
base_dark = """!theme plain
' Google 架构块风格：深色底、实色模块、白字、方角。
skinparam backgroundColor #282A2D
skinparam defaultFontName "Noto Sans CJK SC"
skinparam defaultFontSize 14
skinparam defaultFontColor #E8EAED
skinparam defaultTextAlignment center
skinparam titleFontColor #FFFFFF
skinparam titleFontSize 18
skinparam shadowing false
skinparam roundcorner 0
skinparam ArrowColor #BDC1C6
skinparam ArrowFontColor #E8EAED
skinparam ArrowThickness 1
skinparam note {
    BackgroundColor #3C4043
    BorderColor #5F6368
    FontColor #E8EAED
}
<style>
root {
    LineColor #5F6368
}
arrow {
    LineColor #BDC1C6
    FontColor #E8EAED
    LineThickness 1
}
</style>"""

base_light = """!theme plain
' Google 架构块风格：亮色底（透明适配博客）、实色模块、深色字、方角。
skinparam backgroundColor transparent
skinparam defaultFontName "Noto Sans CJK SC"
skinparam defaultFontSize 14
skinparam defaultFontColor #202124
skinparam defaultTextAlignment center
skinparam titleFontColor #202124
skinparam titleFontSize 18
skinparam shadowing false
skinparam roundcorner 0
skinparam ArrowColor #5F6368
skinparam ArrowFontColor #202124
skinparam ArrowThickness 1
skinparam note {
    BackgroundColor #E8EAED
    BorderColor #BDC1C6
    FontColor #202124
}
<style>
root {
    LineColor #BDC1C6
}
arrow {
    LineColor #5F6368
    FontColor #202124
    LineThickness 1
}
</style>"""

text = text.replace(base_dark, base_light)

# 2. Rectangle/Component/Package
comp_dark = """skinparam rectangle {
    BackgroundColor #34A853
    BorderColor #5F6368
    FontColor #FFFFFF
}
skinparam component {
    BackgroundColor #34A853
    BorderColor #5F6368
    FontColor #FFFFFF
}
skinparam package {
    BackgroundColor #202124
    BorderColor #5F6368
    FontColor #E8EAED
}"""

comp_light = """skinparam rectangle {
    BackgroundColor #34A853
    BorderColor #BDC1C6
    FontColor #FFFFFF
}
skinparam component {
    BackgroundColor #34A853
    BorderColor #BDC1C6
    FontColor #FFFFFF
}
skinparam package {
    BackgroundColor #F1F3F4
    BorderColor #BDC1C6
    FontColor #202124
}"""

text = text.replace(comp_dark, comp_light)

# 3. Sequence
seq_dark = """skinparam sequence {
    ParticipantBackgroundColor #34A853
    ParticipantBorderColor #5F6368
    ParticipantFontColor #FFFFFF
    LifeLineBorderColor #5F6368
    LifeLineBackgroundColor #3C4043
    BoxBackgroundColor #202124
    BoxBorderColor #5F6368
    BoxFontColor #E8EAED
    GroupBackgroundColor #3C4043
    GroupBodyBackgroundColor #202124
    GroupBorderColor #5F6368
    GroupFontColor #FFFFFF
    GroupHeaderFontColor #FFFFFF
    DividerBackgroundColor #3C4043
    DividerBorderColor #5F6368
    DividerFontColor #E8EAED
    ReferenceBackgroundColor #202124
    ReferenceBorderColor #5F6368
    ReferenceFontColor #E8EAED
    ArrowColor #BDC1C6
    ArrowFontColor #E8EAED
}"""

seq_light = """skinparam sequence {
    ParticipantBackgroundColor #34A853
    ParticipantBorderColor #BDC1C6
    ParticipantFontColor #FFFFFF
    LifeLineBorderColor #BDC1C6
    LifeLineBackgroundColor #E8EAED
    BoxBackgroundColor #F1F3F4
    BoxBorderColor #BDC1C6
    BoxFontColor #202124
    GroupBackgroundColor #E8EAED
    GroupBodyBackgroundColor #F1F3F4
    GroupBorderColor #BDC1C6
    GroupFontColor #202124
    GroupHeaderFontColor #202124
    DividerBackgroundColor #E8EAED
    DividerBorderColor #BDC1C6
    DividerFontColor #202124
    ReferenceBackgroundColor #F1F3F4
    ReferenceBorderColor #BDC1C6
    ReferenceFontColor #202124
    ArrowColor #5F6368
    ArrowFontColor #202124
}
skinparam participant<<ext>> {
    BackgroundColor #E8EAED
    FontColor #202124
}"""

text = text.replace(seq_dark, seq_light)

# 4. Activity
act_dark = """skinparam activity {
  BackgroundColor #34A853
  BorderColor #5F6368
  FontColor #FFFFFF
  DiamondBackgroundColor #3C4043
  DiamondBorderColor #5F6368
  DiamondFontColor #E8EAED
  StartColor #BDC1C6
  EndColor #BDC1C6
}
skinparam partition {
  BackgroundColor #202124
  BorderColor #5F6368
  FontColor #E8EAED
}"""

act_light = """skinparam activity {
  BackgroundColor #34A853
  BorderColor #BDC1C6
  FontColor #FFFFFF
  DiamondBackgroundColor #E8EAED
  DiamondBorderColor #BDC1C6
  DiamondFontColor #202124
  StartColor #5F6368
  EndColor #5F6368
}
skinparam partition {
  BackgroundColor #F1F3F4
  BorderColor #BDC1C6
  FontColor #202124
}"""

text = text.replace(act_dark, act_light)

# Fix Sequence Diagram Participants (make sizes uniform and use <<ext>> instead of html tags and hardcoded colors)

text = text.replace('participant "<color:#E8EAED>Application</color>" as App #3C4043', 'participant "Application\\n(App)" as App <<ext>>')
text = text.replace('participant "libscreen.so" as LibScreen', 'participant "libscreen.so\\n(Client)" as LibScreen')
text = text.replace('participant "screen\\nScreen 服务进程" as Screen', 'participant "screen\\n(Server)" as Screen')

text = text.replace('participant "<color:#E8EAED>Application / CPU</color>" as App #3C4043', 'participant "Application\\n(CPU)" as App <<ext>>')
text = text.replace('participant "Window Buffer\\n像素存储" as Buffer #4285F4', 'participant "Window Buffer\\n(Memory)" as Buffer #4285F4')
text = text.replace('participant "<color:#E8EAED>Screen 呈现路径</color>\\n<color:#E8EAED>合成 / 复制 / 直显</color>" as Presentation #3C4043', 'participant "Screen Present\\n(Display)" as Presentation <<ext>>')

text = text.replace('participant "libGLESv2.so" as GLES', 'participant "libGLESv2\\n(GL API)" as GLES')
text = text.replace('participant "libEGL.so" as EGL', 'participant "libEGL.so\\n(Context)" as EGL')
text = text.replace('participant "<color:#E8EAED>GPU</color>" as GPU #3C4043', 'participant "GPU HW\\n(Render)" as GPU <<ext>>')
text = text.replace('participant "screen" as Screen', 'participant "screen\\n(Server)" as Screen')


with open("content/qnx/qnx-screen-graphics-subsystem.md", "w", encoding="utf-8") as f:
    f.write(text)

print("Done")
