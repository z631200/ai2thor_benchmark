# ai2thor_benchmark

專案分成兩個獨立版本：

- [`local/`](local/)：原本的 Python benchmark、測試與歷史範例，原始檔案內容保留。執行前先 `cd local`，詳見 [本機說明](local/README.md)。
- [`colab/AI2_THOR_Scene_Capture.ipynb`](colab/AI2_THOR_Scene_Capture.ipynb)：單一 Google Colab Notebook，包含安裝啟動、3／4 個位置的場景截圖、所有物件座標與朝向匯出，以及 ZIP 下載。使用說明全部放在 Notebook 內。

Git 設定保留在根目錄。原本的本機指令改在 `local/` 下執行，例如：

```sh
cd local
python -m pip install -r requirements.txt
python main.py
python -S -m unittest discover -s tests -v
```
