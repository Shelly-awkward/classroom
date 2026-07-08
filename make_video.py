# -*- coding: utf-8 -*-
"""
make_video.py — 把 PDF 簡報 + 錄音檔離線合成教學影片 (MP4)

搭配 slides-to-video.html 的「邊聽邊點換頁」使用：
  1. 用瀏覽器工具聽錄音、標好每頁開始時間，按「匯出時間表」下載 timeline.json
  2. 跑本腳本，直接壓成 MP4（不用即時播放，秒出）

用法：
  python make_video.py 簡報.pdf 錄音.mp3 timeline.json -o 影片.mp4
  python make_video.py 簡報.pdf 錄音.mp3            # 沒有時間表 → 每頁平均分配
  python make_video.py 簡報.pdf 錄音.mp3 -o out.mp4 --res 1280x720 --fps 24

多個錄音檔：
  # 一頁一個錄音（檔數 = 頁數）→ 全自動，每頁時長 = 該段錄音長度，不需要 timeline
  python make_video.py 簡報.pdf p1.m4a p2.m4a p3.m4a
  # 一段錄音斷成多檔（檔數 ≠ 頁數）→ 自動接起來後照 timeline / 平均分配
  python make_video.py 簡報.pdf 上半.m4a 下半.m4a timeline.json

需求：ffmpeg / ffprobe（全域可用）、pypdfium2、Pillow
"""

import sys
import os
import json
import shutil
import argparse
import tempfile
import subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pypdfium2 as pdfium
from PIL import Image


def die(msg):
    print("錯誤：" + msg)
    sys.exit(1)


def check_tools():
    for exe in ("ffmpeg", "ffprobe"):
        if shutil.which(exe) is None:
            die("找不到 %s，請先安裝 ffmpeg（並確認在 PATH）。" % exe)


def audio_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        die("無法讀取音檔長度：%s" % path)


def concat_audios(paths, tmp):
    """把多個音檔（格式可不同）接成一個 wav，回傳路徑。"""
    if len(paths) == 1:
        return paths[0]
    joined = os.path.join(tmp, "joined.wav")
    cmd = ["ffmpeg", "-y"]
    for p in paths:
        cmd += ["-i", p]
    filt = "".join("[%d:a]" % i for i in range(len(paths)))
    filt += "concat=n=%d:v=0:a=1[a]" % len(paths)
    cmd += ["-filter_complex", filt, "-map", "[a]", joined]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:])
        die("接合音檔失敗。")
    return joined


def load_timeline(path, num_pages, duration):
    """回傳長度 = num_pages 的每頁開始秒數陣列。"""
    if path:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        starts = list(data.get("pageStarts", []))
        # 只取前 num_pages 個；不足的用平均分配補到結尾
        starts = starts[:num_pages]
        if len(starts) < num_pages:
            last = starts[-1] if starts else 0.0
            remain = num_pages - len(starts)
            span = max(0.0, duration - last)
            step = span / (remain + 1)
            for i in range(remain):
                starts.append(last + step * (i + 1))
    else:
        # 沒有時間表：整段錄音平均切給每一頁
        step = duration / num_pages
        starts = [step * i for i in range(num_pages)]

    # clamp + 單調遞增
    for k in range(len(starts)):
        starts[k] = min(max(0.0, float(starts[k])), duration)
        if k > 0 and starts[k] < starts[k - 1]:
            starts[k] = starts[k - 1]
    return starts


def render_pages(pdf_path, W, H, frames_dir):
    """把每頁渲染成 WxH 的黑底置中 (letterbox) PNG，回傳檔名清單。"""
    pdf = pdfium.PdfDocument(pdf_path)
    n = len(pdf)
    if n == 0:
        die("PDF 沒有任何頁面。")
    paths = []
    for i in range(n):
        page = pdf[i]
        w_pt, h_pt = page.get_size()  # points @ 72dpi
        # 讓渲染寬度至少等於目標寬度 (略放大求清晰)，上限 4x 免爆記憶體
        scale = min(max(W / w_pt, H / h_pt) * 1.0, 8.0)
        bitmap = page.render(scale=scale)
        img = bitmap.to_pil().convert("RGB")
        # 等比縮到能塞進 WxH
        fit = min(W / img.width, H / img.height)
        new_w = max(1, round(img.width * fit))
        new_h = max(1, round(img.height * fit))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (W, H), (0, 0, 0))
        canvas.paste(img, ((W - new_w) // 2, (H - new_h) // 2))
        out = os.path.join(frames_dir, "p%04d.png" % i)
        canvas.save(out)
        paths.append(out)
        print("  渲染第 %d/%d 頁" % (i + 1, n))
    return paths


def write_concat_list(frame_paths, starts, duration, list_path):
    """寫 ffmpeg concat demuxer 清單，每頁帶自己的時長。"""
    durations = []
    n = len(frame_paths)
    for i in range(n):
        end = starts[i + 1] if i + 1 < n else duration
        durations.append(max(0.05, end - starts[i]))
    with open(list_path, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        for i, p in enumerate(frame_paths):
            f.write("file '%s'\n" % p.replace("\\", "/").replace("'", "'\\''"))
            f.write("duration %.3f\n" % durations[i])
        # concat demuxer 會忽略最後一個 duration，故重複最後一張讓它生效
        f.write("file '%s'\n" % frame_paths[-1].replace("\\", "/").replace("'", "'\\''"))
    return durations


def main():
    ap = argparse.ArgumentParser(description="PDF + 錄音 → MP4 教學影片")
    ap.add_argument("pdf", help="PDF 簡報路徑")
    ap.add_argument("inputs", nargs="+",
                    help="錄音檔（可多個、依順序），最後一個若是 .json 則視為 timeline")
    ap.add_argument("-o", "--out", help="輸出 MP4 路徑（預設 = PDF 同名 .mp4）")
    ap.add_argument("--res", default=None, help="解析度，如 1920x1080 或 1280x720")
    ap.add_argument("--fps", type=int, default=30, help="影格率（預設 30）")
    args = ap.parse_args()

    # 最後一個位置參數若是 .json → timeline，其餘都是音檔
    audios = list(args.inputs)
    timeline_path = None
    if audios and audios[-1].lower().endswith(".json"):
        timeline_path = audios.pop()
    if not audios:
        die("至少要給一個錄音檔。")
    args.timeline = timeline_path

    check_tools()
    for p in [args.pdf] + audios:
        if not os.path.isfile(p):
            die("找不到檔案：%s" % p)
    if args.timeline and not os.path.isfile(args.timeline):
        die("找不到時間表：%s" % args.timeline)

    # 解析度：優先 CLI，其次 timeline.json，最後預設 1080p
    res = args.res
    if res is None and args.timeline:
        try:
            res = json.load(open(args.timeline, encoding="utf-8")).get("res")
        except Exception:
            res = None
    res = res or "1920x1080"
    try:
        W, H = (int(x) for x in res.lower().split("x"))
    except Exception:
        die("解析度格式錯誤：%s（應為 寬x高，如 1920x1080）" % res)
    W -= W % 2
    H -= H % 2  # H.264 yuv420p 需偶數

    out = args.out or os.path.splitext(args.pdf)[0] + ".mp4"

    pdf = pdfium.PdfDocument(args.pdf)
    num_pages = len(pdf)
    del pdf

    tmp = tempfile.mkdtemp(prefix="classroom_")
    try:
        # ---- 決定音軌與每頁開始時間 ----
        if len(audios) == num_pages and not args.timeline:
            # 一頁一個錄音：每頁時長 = 該段錄音長度，全自動
            print("偵測到 %d 個錄音檔 = %d 頁 → 一頁一段模式（不需 timeline）" % (len(audios), num_pages))
            durs_in = [audio_duration(p) for p in audios]
            starts, acc = [], 0.0
            for d in durs_in:
                starts.append(acc)
                acc += d
            duration = acc
            print("  各段長度：" + ", ".join("%.1f" % d for d in durs_in) + "（共 %.1f 秒）" % duration)
            audio_path = concat_audios(audios, tmp)
        else:
            if len(audios) > 1:
                print("接合 %d 個錄音檔…" % len(audios))
            audio_path = concat_audios(audios, tmp)
            duration = audio_duration(audio_path)
            print("  錄音總長：%.1f 秒" % duration)
            starts = load_timeline(args.timeline, num_pages, duration)

        print("渲染 %d 頁投影片 @ %dx%d…" % (num_pages, W, H))
        frames = render_pages(args.pdf, W, H, tmp)
        list_path = os.path.join(tmp, "list.txt")
        durs = write_concat_list(frames, starts, duration, list_path)
        print("每頁秒數：" + ", ".join("%.1f" % d for d in durs))

        print("用 ffmpeg 合成 MP4…")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(args.fps),
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-2000:])
            die("ffmpeg 失敗。")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    size_mb = os.path.getsize(out) / 1048576
    print("\n完成 ✓  %s  (%.1f MB, %dx%d, %.0f 秒)" % (out, size_mb, W, H, duration))


if __name__ == "__main__":
    main()
