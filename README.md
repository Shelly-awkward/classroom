# classroom

一些自己動手做的教學 / 備課小工具，全部是**純前端**、在瀏覽器裡執行，檔案完全不上傳。

👉 線上使用（GitHub Pages）：<https://shelly-awkward.github.io/classroom/>

## 工具列表

### 🎬 簡報 + 錄音 → 影片 (`slides-to-video.html`)

把一份 **PDF 簡報** 和 **一整段連續錄音**，在瀏覽器裡合成影片（WebM）。

因為一整段錄音無法自動得知何時換頁，所以採用「**邊聽邊點**」的方式：

1. **載入** — 拖入 PDF 與錄音檔。
2. **邊聽邊點換頁** — 播放錄音，每到要換頁的地方就按一下「下一頁」（或按 <kbd>Enter</kbd>）。可事後在時間表手動微調每頁的秒數。
3. **輸出影片** — 選解析度與 FPS，按「開始錄製」，工具會即時把投影片＋聲音錄成一支 WebM，完成後直接下載。

輸出有兩種方式：

**🅐 瀏覽器即時錄製 WebM** — 不用裝任何東西，但 N 分鐘錄音要花約 N 分鐘錄，過程請保持分頁在前景。建議用 **Chrome / Edge**。

**🅑 本機快速壓 MP4（推薦，`make_video.py`）** — 在第 3 步按「⬇ 匯出時間表 JSON」下載 `timeline.json`，再用 ffmpeg 離線秒出 MP4：

```bash
python make_video.py 簡報.pdf 錄音檔.mp3 timeline.json -o 影片.mp4
# 選項：--res 1280x720（預設 1920x1080）  --fps 24（預設 30）
# 沒有 timeline.json 時，會把整段錄音平均分配給每一頁
```

錄音檔可以給**好幾個**（照順序排）：

```bash
# 一頁一個錄音（檔數 = 頁數）→ 全自動：每頁時長 = 該段錄音長度，連 timeline 都不用
python make_video.py 簡報.pdf p1.m4a p2.m4a p3.m4a

# 一段錄音斷成多檔（檔數 ≠ 頁數）→ 自動接起來，再照 timeline / 平均分配
python make_video.py 簡報.pdf 上半.m4a 下半.m4a timeline.json
```

音檔格式不挑：mp3 / m4a（iPhone 語音備忘錄）/ wav / aac 等 ffmpeg 認得的都行，也可混用。

需求：`ffmpeg` / `ffprobe`（全域可用）、`pypdfium2`、`Pillow`（`pip install pypdfium2 Pillow`）。
輸出為 H.264 + AAC 的 MP4，YouTube／各播放器通用，比即時錄製快非常多。

### 🌏 地球演化：板塊漂移與生物 (`earth-evolution.html`)

一顆會自轉的地球，從 **46 億年前的冥古宙** 一路播放到現在，用來上課時當背景動畫或讓學生自己拉著玩。

- 陸塊隨年代**聚合又裂解**（盤古大陸 → 大西洋張開 → 印度北漂），海洋顏色、冰帽範圍也跟著變。
- 右側同步顯示該年代的**地質事件**與**當時的生物**（三葉蟲、恐龍、猛獁象……皆為手繪 SVG 圖示）。
- 可**暫停**、拖**時間軸**跳到任一年代；播到第四紀會用紅點標出**台灣**——約 600 萬年前蓬萊造山運動才讓它浮出海面。

> 板塊位置為教學用示意，非古地理學精確重建。

## 技術

- PDF 在瀏覽器端以 [pdf.js](https://github.com/mozilla/pdf.js)（已 vendored 於 `vendor/`）渲染；`make_video.py` 端則用 `pypdfium2` 渲染。
- WebM 以瀏覽器原生 `<canvas>.captureStream()` + `MediaRecorder` 即時合成，無需後端。
- MP4 由 `make_video.py`：`pypdfium2` 把每頁 letterbox 成圖 → ffmpeg concat（每頁帶自己的時長）+ 音軌 → H.264/AAC。
- `earth-evolution.html` 為單檔純 JS + `<canvas>`（正射投影自繪地球，無任何函式庫、無外部資源），可直接離線開啟。
