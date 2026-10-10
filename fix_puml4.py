with open("content/qnx/qnx-screen-graphics-subsystem.md", "r", encoding="utf-8") as f:
    text = f.read()

comp_light_old = """skinparam package {
    BackgroundColor #F1F3F4
    BorderColor #BDC1C6
    FontColor #202124
}"""

comp_light_new = """skinparam packageBackgroundColor #F1F3F4
skinparam packageBorderColor #BDC1C6
skinparam packageFontColor #202124
skinparam package {
    BackgroundColor #F1F3F4
    BorderColor #BDC1C6
    FontColor #202124
}"""

text = text.replace(comp_light_old, comp_light_new)

with open("content/qnx/qnx-screen-graphics-subsystem.md", "w", encoding="utf-8") as f:
    f.write(text)
print("Fixed packageFontColor")
