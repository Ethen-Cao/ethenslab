with open("content/qnx/qnx-screen-graphics-subsystem.md", "r", encoding="utf-8") as f:
    text = f.read()

comp_light_old = """skinparam package {
    BackgroundColor #F1F3F4
    BorderColor #BDC1C6
    FontColor #202124
}"""

comp_light_new = """skinparam package {
    BackgroundColor #F1F3F4
    BorderColor #BDC1C6
    FontColor #202124
}
skinparam rectangle<<ext>> {
    BackgroundColor #E8EAED
    FontColor #202124
}"""

text = text.replace(comp_light_old, comp_light_new)
text = text.replace('rectangle "<color:#E8EAED>Application</color>\\n<color:#E8EAED>窗口管理与绘制</color>" as App #3C4043', 'rectangle "Application\\n(App)" as App <<ext>>')

with open("content/qnx/qnx-screen-graphics-subsystem.md", "w", encoding="utf-8") as f:
    f.write(text)

print("Done2")
