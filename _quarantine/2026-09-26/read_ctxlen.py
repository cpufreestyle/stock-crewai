import mmap, struct

blob = r"C:\Users\qm081\.ollama\models\blobs\sha256-29e5614f2813e329ddd50929eb45766daaa507e0a7daccfc41aea00ed865a684"
out = r"D:\aishare\repo\stock-crewai-master\ctxlen_result.txt"
results = []
with open(blob, "rb") as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    # GGUF key 精确匹配: uint64 长度=15 后跟 "llama.context_length"
    prefix = struct.pack("<Q", 15) + b"llama.context_length"
    idx = mm.find(prefix)
    results.append(f"prefix idx = {idx}")
    if idx < 0:
        results.append("未找到精确前缀，尝试宽泛搜索")
        idx2 = mm.find(b"llama.context_length")
        results.append(f"宽泛 idx = {idx2}")
    else:
        val_off = idx + len(prefix) + 4  # skip uint32 value_type
        vt = struct.unpack("<I", mm[idx + len(prefix): idx + len(prefix) + 4])[0]
        if vt == 4:
            val = struct.unpack("<I", mm[val_off:val_off+4])[0]
            results.append(f"value_type=UINT32(4), context_length={val}")
        elif vt == 5:
            val = struct.unpack("<Q", mm[val_off:val_off+8])[0]
            results.append(f"value_type=UINT64(5), context_length={val}")
        else:
            results.append(f"value_type={vt} (未知)")
    mm.close()

with open(out, "w", encoding="utf-8") as w:
    w.write("\n".join(results))
print("done")
