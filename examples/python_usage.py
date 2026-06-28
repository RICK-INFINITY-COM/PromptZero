from promptzero import clean, stats

text = "嗯，那个，就是说，请问你能不能帮我写一个 Python 脚本，非常非常感谢！！"
cleaned = clean(text, level="moderate")
print(cleaned)
print(stats(text, cleaned))
