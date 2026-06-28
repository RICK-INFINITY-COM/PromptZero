from promptzero import clean


def test_chinese_safe_keeps_reference_words():
    assert clean("那个文件在桌面上，帮我看看") == "那个文件在桌面上，帮我看看"


def test_chinese_moderate_removes_politeness():
    assert clean("嗯嗯呃，那个那个，我就是想说，能不能麻烦你帮我看看这个问题？谢谢啦！！", level="moderate") == "帮我看看这个问题？"


def test_english_moderate():
    assert clean("Um, you know, I was just wondering if you could help me?", level="moderate") == "please help me?"


def test_code_block_is_preserved():
    source = "嗯，帮我优化：\n```python\n# 嗯，这里别删\nx = 1\n```"
    out = clean(source, level="moderate")
    assert "# 嗯，这里别删" in out
