import mmap

blob = r"C:\Users\qm081\.ollama\models\blobs\sha256-29e5614f2813e329ddd50929eb45766daaa507e0a7daccfc41aea00ed865a684"
needle = b"enable_thinking is undefined or enable_thinking is true"
needle2 = b"enable_thinking is defined and enable_thinking is true"

with open(blob, "rb") as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    data = mm
    cnt = 0
    i = 0
    while True:
        j = data.find(needle, i)
        if j < 0:
            break
        cnt += 1
        print(f"undefined-or-true 第{cnt}次 @ {j}: ...{data[j-40:j+len(needle)+40].decode('utf-8','replace')}...")
        i = j + 1
    print("undefined-or-true 总次数:", cnt)
    idx2 = data.find(needle2)
    print("defined-and-true 出现位置:", idx2)
    mm.close()
