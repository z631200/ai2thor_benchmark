# ai2thor_benchmark

專案包含建圖流程與兩種模擬器執行方式：

- 根目錄的 `run_scene_graph.py`：讀取已匯出的四視角資料，使用本機 Ollama 完成階段 1–3 建圖。
- [`local/`](local/)：原本的 Python benchmark、測試與歷史範例，原始檔案內容保留。執行前先 `cd local`，詳見 [本機說明](local/README.md)。
- [`colab/AI2_THOR_Scene_Capture.ipynb`](colab/AI2_THOR_Scene_Capture.ipynb)：單一 Google Colab Notebook，包含安裝啟動、3／4 個位置的場景截圖、所有物件座標與朝向匯出，以及 ZIP 下載。使用說明全部放在 Notebook 內。

Git 設定保留在根目錄。原本的本機指令改在 `local/` 下執行，例如：

```sh
cd local
python -m pip install -r requirements.txt
python main.py
python -S -m unittest discover -s tests -v
```


## 多視角建圖（階段 1–3）

第一版完成階段 1–3，以下程式置於專案根目錄。透過本機 `http://localhost:11434` 呼叫 `gemma4:e4b`；四個觀察者使用 README 的相同英文 prompt，只替換圖片與視角 ID，依序執行且不共享對話。模型回答全部使用英文。

| 檔案 | 功能 |
| --- | --- |
| `run_scene_graph.py` | CLI、讀取場景、執行三階段、儲存結果與續跑。 |
| `ollama_client.py` | 傳送圖片與文字、呼叫模型、處理逾時及記錄用量。 |
| `scene_prompts.py` | 英文共通規則、階段 1–3 prompt 與關係定義。 |
| `scene_validation.py` | 解析文字格式、記錄可確定的欄位正規化，並檢查 ID、三元組與來源。 |
| `tests/test_scene_graph.py` | 使用模擬回答測試流程、資料隔離與錯誤處理。 |

### 執行方式

根目錄建圖程式只需 Python 3.10+ 標準函式庫，不需安裝 AI2-THOR。先啟動本機 Ollama（服務已啟動可略過），並準備模型：

```sh
ollama serve
# 在另一個終端執行；模型已安裝可略過：
ollama pull gemma4:e4b
```

```sh
python run_scene_graph.py --scene-dir colab/scene_output/20261021T030626_636386Z
# 所有階段啟用推論，並允許較多格式修正：
python run_scene_graph.py --scene-dir colab/scene_output/20261021T030626_636386Z --thinking on --format-retries 5
# 只檢查輸入並輸出 prompt，不連線模型：
python run_scene_graph.py --scene-dir colab/scene_output/20261021T030626_636386Z --dry-run
# 中斷後沿用原設定，將 RUN_DIRECTORY 替換為先前顯示的 run 目錄：
python run_scene_graph.py --scene-dir colab/scene_output/20261021T030626_636386Z --resume RUN_DIRECTORY
# 修正程式後，從舊 run 建立新 run，重新驗證並重用前兩階段：
python run_scene_graph.py --scene-dir colab/scene_output/20261021T030626_636386Z --fork-from RUN_DIRECTORY --stage 3 --thinking on
# 不需模型的回歸測試：
python -S -m unittest discover -s tests -v
```

| 參數 | 預設／功能 |
| --- | --- |
| `--stage` | `all`；可選 `1`、`2`、`3`，後兩者需 `--resume` 或 `--fork-from` 且先前階段已通過檢查。 |
| `--fork-from` | 修正程式後建立新 run，核對原設定與輸入、重驗已完成結果，保留舊 run；可搭配 `--stage 3`。 |
| `--model`、`--ollama-url` | `gemma4:e4b`、`http://localhost:11434`。 |
| `--output-dir` | 專案根目錄的 `outputs/`，每次新增獨立目錄。 |
| `--timeout`、`--format-retries` | 每次 HTTP 請求 600 秒；每個任務格式修正最多 3 次。 |
| `--num-ctx`、`--num-predict` | 上下文 32768、最大輸出 8192 tokens；依記憶體調整。 |
| `--temperature`、`--seed` | `0.2`、`42`；保存設定，但不保證跨硬體／版本逐字重現。 |
| `--thinking` | `auto`：支援 reasoning 的模型僅在中央文字任務啟用；另可選 `on`、`off`。 |
| `--verification-budget` | 最多提出 4 個查證問題，僅保存、不執行。 |

續跑會核對輸入、程式、模型 digest、生成參數及已完成檔案；程式有變更可用 `--fork-from` 建立新 run，但需沿用來源 run 的模型與生成參數（如 `--thinking on`）。HTTP 錯誤、格式修正耗盡或輸出截斷會停止並保存診斷；完全相同的錯誤回答重複出現會提前停止。變更 token 設定須開新 run。若強制終止留下 `.run.lock`，確認沒有程序使用該目錄後才移除。

若看到 `invalid reference frame`，`image_left_of`／`closer_to_camera` 的 frame 應是來源 `view_N`，`on`／`inside` 則為 `physical`。程式只在來源、端點與視角可唯一確定時修正別名，並合併完全相同的邊、保留來源與較保守狀態；錯誤視角或歧義仍須修正。詳見 [格式與正規化規則](docs/output_format.md)。

模型使用固定段落與文字欄位，詳見 [輸出格式](docs/output_format.md)。英文 prompt 取自下方 README，格式要求附加於 `scene_prompts.py`；修改 README 不會自動變更程式 prompt。圖片使用官方 [Ollama images API](https://docs.ollama.com/capabilities/vision) 傳送。

### 輸出檔案

每次執行保存至 `outputs/<run_id>/`：

| 輸出 | 內容 |
| --- | --- |
| `observations/view_1.md`～`view_4.md` | 各視角的物件、關係、證據與不確定事項。 |
| `correspondence.md` | 局部到全域物件的對應、候選與理由。 |
| `scene_graph.md` | 三元組（如 `(g1, on, g2)`）、參考系、狀態、來源及待查證問題。 |
| `prompts/`、`responses/` | 實際文字 prompt、原始回答、格式修正與 Ollama 回應。 |
| `camera_metadata.json` | 僅含允許送入中央模型的相機資訊。 |
| `normalizations/` | frame 修正、重複邊合併與前後雜湊；原始回答保留於 `responses/`。 |
| `validation_report.json`、`run_manifest.json` | 程式檢查結果、模型參數、輸入雜湊與執行用量。 |

## 資料與建圖流程

```mermaid
flowchart TD
    A["AI2-THOR<br/>靜態場景"] --> B["Colab 擷取<br/>四視角資料"]
    B --> C["下載場景資料"]
    C --> I["四張 RGB 圖片"]
    C --> V["相機資訊<br/>views.json"]
    C --> T["物件真值<br/>僅供評分"]
    I --> S1["1. 局部觀察<br/>四次獨立 VLM 呼叫"]
    S1 --> O["四份局部觀察"]
    O --> S2["2. 物件對應<br/>中央 LLM"]
    V --> S2
    S2 --> S3["3. 初步建圖<br/>中央 LLM"]
    O --> S3
    V --> S3
    R["英文 Prompt<br/>與關係定義"] --> S1
    R --> S2
    R --> S3
    S3 --> K["檢查並儲存<br/>Scene graph"]
    K -.-> E["獨立評分<br/>後續實作"]
    T -.-> E
```

圖中僅列步驟名稱，檔案與各階段輸入／輸出詳見表格。下載資料放在 `colab/scene_output/<場景資料夾>/`。

正常流程共六次模型呼叫，格式錯誤時每個任務預設最多重試三次；`objects.json/.csv` 與 `views.json` 的真值物件總數不進入 prompt。相機位置使用 `cameraPosition`。本版只提出查證請求，不執行階段 4–5；建圖不需啟動 AI2-THOR。程式檢查驗證格式與來源引用，不保證辨識正確。

# 多視角 VLM 空間建圖：研究目標與階段 Prompt

## 一、研究目標

在同一間靜態模擬房間（如 AI2-THOR）四角配置相機，由四個 VLM 分別觀察。允許各 VLM 出現辨識錯誤、遺漏與關係誤判，再由中央 LLM 整合描述、處理衝突並定向查證，建立可追溯、可更新的 scene graph，支援後續空間問答或物件定位。

核心問題：**跨視角整合與定向查證，能否比單一視角或單次整合，更準確地建立可重複使用的空間表示？**

本設計將 scene graph 作為可檢查的外部空間記憶；下游表現可用於評估其效用，但不能單憑建圖結果證明模型內部已形成 cognitive／mental map。

## 二、流程與資料邊界

階段 0 已由 Colab Notebook 提供；本版實作階段 1–3 與程式檢查，階段 4–6 留待後續。以下建圖輸出路徑皆相對於 `outputs/<run_id>/`。

| 階段 | 執行者 | 預期輸入 | 預期輸出 |
| --- | --- | --- | --- |
| 0. 資料擷取 | Colab／AI2-THOR | 場景名稱、四個拍攝位置與相機設定 | `colab/scene_output/<場景資料夾>/`：四張 `view_01.png`～`view_04.png`、`views.json`；另存評分真值 `objects.json/.csv`。 |
| 1. 局部觀察 | 四個獨立 VLM | 每次一張原圖、`view_1`～`view_4`、相同英文共通規則與階段 1 prompt | `observations/view_1.md`～`view_4.md`：局部物件 ID、屬性、關係 ID、參考視角、可見證據與不確定事項。 |
| 2. 物件對應 | 中央 LLM | 四份局部觀察、篩選後的相機資訊、英文共通規則與階段 2 prompt | `correspondence.md`：全域物件 `g1…`、每個局部 ID 的對應或候選、來源、匹配理由與歧義。 |
| 3. 初步建圖 | 中央 LLM | 四份局部觀察、`correspondence.md`、相機資訊、關係定義、查證問題上限、英文共通規則與階段 3 prompt | `scene_graph.md`：節點、`(g1, on, g2)` 等三元組、邊 ID、參考系、狀態、證據來源、衝突與查證請求。 |
| 程式檢查與紀錄 | Python | 各階段文字結果、ID／關係規則、呼叫紀錄 | `validation_report.json`：格式與引用檢查結果；`run_manifest.json`：模型、參數、輸入雜湊及用量；`prompts/`：實際文字 prompt。 |
| 4. 定向查證（後續） | 指定 VLM | 自己的原圖、原局部觀察、特定查證問題 | 支持／反對／無法判斷、可見證據、沿用原 ID 的修正與新發現。 |
| 5. 更新定稿（後續） | 中央 LLM＋程式 | 目前圖與對應、原局部觀察、查證結果、相機與關係定義、剩餘預算 | 更新圖與對應、修改紀錄、未解問題、停止或繼續查證的決定。 |
| 6. 下游任務（後續） | 固定任務模型 | 定稿圖、新問題、關係定義 | 答案或計畫、依據的節點／邊 ID、可回答／部分可回答／資訊不足。 |

相機資訊僅含 `cameraPosition`、agent yaw、`cameraHorizon`、FOV、座標系與單位；階段 1 不接收相機資訊或其他視角觀察，階段 2–3 不接收原圖或物件真值。模型結果為英文自然語言、對應表與三元組，JSON 紀錄由程式產生。

階段 0 不需要 prompt。階段 4–5 可循環，但由程式限制總查證次數與輪數。中央 LLM 可使用同一模型分次執行。

- **模型可用資料**：圖片及其觀察、相機位置與朝向、座標系與關係定義。第一階段 VLM 只做局部描述，相機資訊交由中央模型整合。
- **評分專用資料**：模擬器真實物件 ID、座標、包圍盒、容器關係及標準答案；不得放入建圖或下游 prompt。
- **格式**：VLM 全程使用自然語言，不使用 JSON；中央 LLM 使用固定段落、對應表與關係三元組。
- **命名**：視角 view_1～view_4；局部物件 v1_o1；局部關係 v1_r1；全域物件 g1；圖邊 e1。ID 一經指派即保留，修正須可追溯。
- **影像**：階段 1、4 必須實際附上圖片，不能只提供檔名。
- **使用方式**：每次選中文或英文，將下列「共通規則」與該階段 prompt 一起送入模型，並填入所有變數。

## 三、共通規則

### 中文版

~~~text
只使用本次提供的資料；觀察與模型回答皆可能有錯。
每項主張須有來源，區分直接觀察與推導；證據不足時保留未知或候選。
未看見不等於不存在，未記錄關係不等於關係為假。
嚴格區分畫面方向、相機深度、物理關係及世界座標方向，保留參考視角或座標系。
畫面上方不等於物理高度較高，也不等於受到支撐。
不臆測精確三維座標或距離；相機姿態加上畫面左右通常不足以唯一決定三維位置。
沿用既有 ID，保留來源與不確定性；不以多數票、重複描述或模型一致作為正確性的充分證據。
~~~

### English

~~~text
Use only the supplied information. Observations and model responses may be wrong.
Preserve sources and distinguish observations from inferences. Keep unknowns or alternatives when evidence is insufficient.
Not seeing an object does not establish its absence; a missing relation does not establish that it is false.
Distinguish image directions, camera-relative depth, physical relations, and world-coordinate directions. Preserve the view or reference frame.
Being higher in the image does not imply greater physical height or physical support.
Do not invent precise 3D coordinates or distances. Camera poses and image-left/right relations generally do not uniquely determine 3D positions.
Preserve existing IDs, provenance, and uncertainty. Majority vote, repeated claims, or model agreement alone do not establish correctness.
~~~

## 四、各階段 Prompt

### 階段 1：局部觀察

四個 VLM 各自執行，只替換圖片與視角 ID，不讀取其他視角的描述。

**中文版**

~~~text
你是視角 {view_id} 的局部觀察者。只根據附上的圖片，以自然語言與條列描述，不使用 JSON。

列出可辨識物件並分配局部 ID；相似物件仍須分開編號。
保留有助跨視角辨識的種類、顏色、形狀、特殊標記、畫面位置與遮擋情況，不補猜看不清的屬性。
只列有視覺線索支持的關係，不必列出所有物件配對；深度、支撐、包含與遮擋關係須有相應證據。

輸出：
1. 觀察條件：視角 ID、清晰度與主要限制。
2. 物件：局部 ID；名稱；可見特徵；畫面位置；遮擋。
3. 關係：關係 ID；兩個物件 ID；自然語言關係；參考方式（畫面／相機深度／物理）；明確或暫定；簡短可見證據。
4. 不確定事項：無法辨識、區分或確認的內容。
~~~

**English**

~~~text
You are the local observer for {view_id}. Use only the attached image. Write natural-language descriptions and bullets, not JSON.

List recognizable objects with local IDs; assign separate IDs to similar objects.
Describe visible category, color, shape, distinctive markings, image location, and occlusion useful for cross-view matching. Do not invent unclear attributes.
Report only visually supported relations; do not enumerate all object pairs. Depth, support, containment, and occlusion require appropriate visual cues.

Output:
1. Observation conditions: view ID, clarity, and major limitations.
2. Objects: local ID; name; visible attributes; image location; occlusion.
3. Relations: relation ID; two object IDs; natural-language relation; reference type (image / camera depth / physical); clear or tentative; brief visible evidence.
4. Uncertainties: what cannot be identified, distinguished, or confirmed.
~~~

### 階段 2：跨視角物件對應

先確認「是否為同一實體」，再整合關係。

**中文版**

~~~text
將同一間靜態房間的多視角觀察對應到全域物件。
相機資訊：{camera_metadata}
各視角觀察：{local_observations}

綜合外觀、特殊特徵、周邊關係與相機資訊，建立全域 ID；不可只因名稱或顏色相同就合併。
同一視角中分開列出的物件原則上保持不同；疑似重複偵測列為待查證。
每個局部 ID 都須有對應或未解決候選。證據不足不強行匹配，也不建立沒有局部觀察支持的新物件。

輸出：
1. 全域物件：全域 ID；類別與屬性；局部 ID；暫時接受或待確認；來源與簡短理由。
2. 對應表：每個局部 ID → 全域 ID 或候選集合。
3. 歧義：歧義 ID；涉及物件；可能解釋；缺少證據；可查證的視角與問題。
~~~

**English**

~~~text
Match observations from multiple views of one static room to global objects.
Camera information: {camera_metadata}
Local observations: {local_observations}

Assign global IDs using appearance, distinctive attributes, neighboring relations, and camera information. Do not merge objects solely because their names or colors match.
Keep separately listed objects within one view distinct unless a suspected duplicate detection is verified.
Account for every local ID with a mapping or unresolved candidates. Do not force matches or create objects unsupported by local observations.

Output:
1. Global objects: global ID; category and attributes; local IDs; provisionally accepted or unresolved; sources and brief rationale.
2. Mapping: every local ID → global ID or candidate set.
3. Ambiguities: ambiguity ID; affected objects; possible explanations; missing evidence; a useful view and verification question.
~~~

### 階段 3：初步建圖與查證規劃

**中文版**

~~~text
根據下列資料建立初版 scene graph，並提出必要查證。
相機資訊：{camera_metadata}
局部觀察：{local_observations}
物件對應：{object_correspondence}
允許的關係、參考系與推導規則：{relation_definitions}
本輪查證問題上限：{verification_budget}

以全域 ID 建圖。涉及未確定對應的關係須標記其候選或條件，不得當成確定事實。
只有對象、關係定義與參考系可比較時，才能判定衝突；不同視角的左右相反未必矛盾。
只使用定義允許的推導規則，不假設所有關係都有傳遞性。
查證問題須中立、具體、可由指定 VLM 查看原圖回答；不透露其他模型答案。
優先查證影響多個物件或關係的問題；圖片無法解決者保留資訊不足。

輸出：
1. 節點：全域 ID；類別與屬性；來源；對應狀態。
2. 邊：邊 ID；（主體，關係，客體）；參考系；暫時接受／待確認／衝突；直接觀察或推導；來源視角與關係 ID；推導前提（如有）。
3. 未解問題：問題 ID；類型；涉及節點或邊；缺少資訊或衝突。
4. 查證請求：請求 ID；目標視角；局部物件 ID；中立問題。不得超過上限。
~~~

**English**

~~~text
Build an initial scene graph and propose useful verification requests.
Camera information: {camera_metadata}
Local observations: {local_observations}
Object correspondences: {object_correspondence}
Allowed relations, reference frames, and inference rules: {relation_definitions}
Maximum requests this round: {verification_budget}

Use global IDs. Mark relations involving unresolved correspondences with their alternatives or conditions; do not treat them as established facts.
Declare conflicts only when objects, relation definitions, and reference frames are comparable. Opposite left/right descriptions across views need not conflict.
Apply only permitted inference rules; do not assume all relations are transitive.
Ask neutral, specific questions answerable from the selected VLM's original image without revealing other models' answers.
Prioritize issues affecting multiple objects or relations. Preserve insufficient information when the images cannot resolve it.

Output:
1. Nodes: global ID; category and attributes; sources; correspondence status.
2. Edges: edge ID; (subject, relation, object); reference frame; provisionally accepted / unresolved / conflicting; observed or derived; source view and relation IDs; inference premises if applicable.
3. Unresolved issues: issue ID; type; affected nodes or edges; missing information or conflict.
4. Verification requests: request ID; target view; local object IDs; neutral question. Stay within the limit.
~~~

### 階段 4：指定 VLM 回看原圖

只送出該視角的問題與資料。

**中文版**

~~~text
你是視角 {view_id} 的查證者。重新查看附上的原圖，以自然語言回答，不使用 JSON。
先前局部觀察：{original_local_observation}
查證請求：{verification_request}

只回答本次問題。先前描述可能有錯，不能當成視覺證據；問題提及的物件或關係也不一定存在。
沿用局部物件與關係 ID；新發現使用未使用的 ID。
若目標不明確，指出歧義；若遮擋、解析度或視角不足，回答無法判斷。

輸出：
請求 ID；
結果：支持／反對／無法判斷／目標有歧義（開放問題直接描述結果）；
直接回答與一至兩句可見證據；
修正：原 ID 與替代描述，或「無」；
新發現：新 ID 與描述，或「無」。
~~~

**English**

~~~text
You are the verifier for {view_id}. Re-examine the attached original image. Use natural language, not JSON.
Earlier local observation: {original_local_observation}
Verification request: {verification_request}

Answer only this request. Earlier descriptions may be wrong and are not visual evidence. Objects or relations mentioned in the question may not exist.
Preserve local object and relation IDs; assign unused IDs to new discoveries.
State ambiguity if the target is unclear. Answer “cannot determine” when occlusion, resolution, or viewpoint prevents judgment.

Output:
Request ID;
Outcome: supports / contradicts / cannot determine / ambiguous target (describe observations directly for open questions);
Direct answer with one or two sentences of visible evidence;
Corrections: original IDs and replacement descriptions, or “none”;
New findings: new IDs and descriptions, or “none.”
~~~

### 階段 5：更新圖與停止判斷

**中文版**

~~~text
根據查證結果更新物件對應與 scene graph。
相機資訊與關係定義：{camera_and_relation_definitions}
原始局部觀察：{local_observations}
目前對應表與圖：{current_graph}
查證結果：{verification_results}
剩餘查證問題數：{remaining_budget}

評估新回答的證據，不因其較新就自動採信；同一視角對同一圖片的重複回答不算獨立證據。
合併或拆分物件後，更新受影響的邊並保留舊 ID 去向；推導前提改變時重新檢查結論。
對應可靠、證據足夠且無未解反證者標記「接受」；這是模型判定，不是真值。
保留待確認與有證據的衝突，不為表面一致而刪除。
預算耗盡或無望取得新有效證據時停止；否則提出剩餘預算內的中立問題。

輸出：
1. 更新對應表：所有局部 ID 的去向與候選。
2. 更新圖：沿用階段 3 的節點、邊與證據欄位，邊狀態改為接受／待確認／衝突。
3. 修改紀錄：新增、修正、撤回、合併或拆分，以及證據。
4. 未解問題。
5. 下一步：停止／繼續查證；理由；後續請求（如有）。
~~~

**English**

~~~text
Update object correspondences and the scene graph using verification results.
Camera information and relation definitions: {camera_and_relation_definitions}
Original local observations: {local_observations}
Current mapping and graph: {current_graph}
Verification results: {verification_results}
Remaining number of requests: {remaining_budget}

Evaluate new evidence rather than automatically trusting the newest answer. Repeated answers about the same image from the same view are not independent evidence.
After merging or splitting objects, update affected edges and retain old-ID mappings. Recheck inferences when their premises change.
Mark relations “accepted” only with reliable correspondence, sufficient evidence, and no unresolved counterevidence. Acceptance is a model judgment, not ground truth.
Preserve unresolved claims and evidence-supported conflicts rather than forcing consistency.
Stop when the budget is exhausted or no new useful evidence is expected; otherwise propose neutral questions within the remaining budget.

Output:
1. Updated mapping: every local ID and unresolved candidates.
2. Updated graph: retain Stage 3 node, edge, and evidence fields; use accepted / unresolved / conflicting edge statuses.
3. Edit history: additions, corrections, retractions, merges, or splits, with evidence.
4. Unresolved issues.
5. Next action: stop / continue verification; reason; further requests if any.
~~~

### 階段 6：使用定稿圖完成新任務

建圖時不提前提供下游問題，以測試圖是否能重複使用。

**中文版**

~~~text
只根據定稿 scene graph 完成任務。
定稿圖：{final_scene_graph}
關係定義：{relation_definitions}
新問題或任務：{downstream_task}

不讀取原圖、局部描述或模擬器真值，也不修改圖。
只以已接受的關係作為確定前提，依允許規則推導；不以常識補出缺少的場景事實。
無法唯一辨識目標時列出候選。若缺少距離、通行區域或其他必要資訊，明確指出。

輸出：
狀態：可回答／部分可回答／資訊不足；
答案或計畫；
依據：節點與邊 ID、簡短說明；
限制：缺少資訊與不確定性，或「無」。
~~~

**English**

~~~text
Complete the task using only the finalized scene graph.
Final graph: {final_scene_graph}
Relation definitions: {relation_definitions}
New question or task: {downstream_task}

Do not access original images, local descriptions, or simulator ground truth, and do not modify the graph.
Use only accepted relations as established premises and apply permitted inference rules. Do not fill missing scene facts using common sense.
List candidates if the target is not unique. Identify missing distances, traversable space, or other required information.

Output:
Status: answerable / partially answerable / insufficient information;
Answer or plan;
Evidence: node and edge IDs with a brief explanation;
Limitations: missing information and uncertainty, or “none.”
~~~

## 五、必要設定與評估建議

### 關係定義先固定

在實驗前填妥 {relation_definitions}：每個關係的名稱、方向、參考系、判定條件、是否互斥及允許的推導規則。以下僅為命名示例：

| 關係 | 意義與參考系 |
| --- | --- |
| image_left_of(A, B) | 在指定 view 中，A 位於 B 的畫面左側；不可直接當成世界座標方向 |
| closer_to_camera(A, B) | 相對指定相機，A 比 B 更近；與畫面大小不同 |
| on(A, B) | A 放在 B 表面並受到支撐；不是單純畫面上方 |
| inside(A, B) | A 位於 B 內部；須預先明定部分包含如何處理 |

真值計算也須使用相同定義；不能只靠物件中心座標判定支撐或包含。圖若要支援導航，需另建可通行區域或導航拓樸。

### 最小實驗設計

1. **比較組**：單視角建圖、四視角單次整合（階段 1–3）、四視角整合加查證（階段 1–5）。固定模型、資料與下游題目，記錄各組成本。
2. **錯誤來源**：先評估 VLM 自然錯誤，再額外注入可控的辨識、對應或關係錯誤，分別測試修復能力。
3. **評估項目**：物件對應品質、關係 precision／recall、未知或衝突比例、查證修正與新引入錯誤、下游任務正確率及呼叫成本。正確率須搭配回答覆蓋率，避免大量回報未知造成假性提升。
4. **程式檢查**：確認 ID 存在、局部物件皆有去向、邊引用有效、狀態合法、推導前提可追溯，並強制執行查證預算。格式與邏輯一致不代表圖符合真實場景。

建議先完成階段 1–3 的 baseline，再加入查證與更新；整個評分流程獨立讀取真值，不回饋給建圖模型。
