import mmap, sys

blob = r"C:\Users\qm081\.ollama\models\blobs\sha256-29e5614f2813e329ddd50929eb45766daaa507e0a7daccfc41aea00ed865a684"
off = 10936727
old = b"enable_thinking is undefined or enable_thinking is true"
# 同长(57)替换：末尾补一个空格，语义为"仅当显式 enable_thinking=true 才思考"->默认不思考
new = b"enable_thinking is defined and enable_thinking is true "

assert len(old) == len(new), f"长度不等: {len(old)} vs {len(new)}"

with open(blob, "r+b") as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_WRITE)
    cur = mm[off:off+len(old)]
    if cur != old:
        print("ERROR: 当前字节与预期不符:", cur)
        sys.exit(1)
    mm[off:off+len(new)] = new
    mm.flush()
    after = mm[off:off+len(new)]
    assert after == new, after
    # 确认旧的已不存在
    assert mm.find(old) == -1, "旧串仍残留"
    print("PATCH OK; 新串出现于:", mm.find(new))
    mm.close()
