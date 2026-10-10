with open("content/qnx/qnx-screen-graphics-subsystem.md", "r", encoding="utf-8") as f:
    text = f.read()

# Remove hardcoded box color
text = text.replace('box "Screen 客户端 / 服务端" #202124', 'box "Screen 客户端 / 服务端"')
text = text.replace('box "Screen 渲染接口与资源" #202124', 'box "Screen 渲染接口与资源"')
text = text.replace('box "应用进程内的图形接口" #202124', 'box "应用进程内的图形接口"')
text = text.replace('box "窗口与呈现服务" #202124', 'box "窗口与呈现服务"')

# Add hide stereotype to the seq_light block
seq_light_old = """skinparam participant<<ext>> {
    BackgroundColor #E8EAED
    FontColor #202124
}"""

seq_light_new = """skinparam participant<<ext>> {
    BackgroundColor #E8EAED
    FontColor #202124
}
hide stereotype"""

text = text.replace(seq_light_old, seq_light_new)

# Add hide stereotype to the comp_light block as well just in case
comp_light_old = """skinparam rectangle<<ext>> {
    BackgroundColor #E8EAED
    FontColor #202124
}"""

comp_light_new = """skinparam rectangle<<ext>> {
    BackgroundColor #E8EAED
    FontColor #202124
}
hide stereotype"""

text = text.replace(comp_light_old, comp_light_new)


with open("content/qnx/qnx-screen-graphics-subsystem.md", "w", encoding="utf-8") as f:
    f.write(text)
print("Fixed")
