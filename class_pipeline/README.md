# class_pipeline — 职业整图制 GPT 工作流（独立产线）

> 2D 职业驱动角色产线：每个职业 = 一套完整动作的整图 sprite（DNF/梦幻西游 式），
> 不是分层纸娃娃（gpt_sheet_pipeline 产线）。**本目录自包含零依赖**：脚本、密钥、
> 资产、文档全部在本目录内闭环，不 import、不引用 gpt_sheet_pipeline 任何内容。
> 最后更新: 2026-11-27 · 维护者: lff2116788383 + Doubao 协作会话

## 1. 为什么独立成线（方案决策记录）

| 方案 | 结论 | 依据 |
|---|---|---|
| **职业整图制（本产线）** | ✅ 选定 | 分层省空间的前提是"部件被多角色复用"，职业制的衣/发/武器每职业不同、复用率≈0，分层反而大 3-5 倍；遮挡（刀盖手/盔压发）绘制时逐帧解决，问题不存在；甩辫/袍摆等形变逐帧画进图里（分层 IoU 0.44 画不出）；客户端零图层逻辑 |
| 分层纸娃娃（gpt_sheet_pipeline） | 保留但不扩展 | 12 张内置卡+工具仍有价值；工具兼作烘焙产线（分层摆好→离线合成→整图导出） |
| 像素骨骼 | 不采用 | 省空间但丢形变（attack 甩辫 IoU 0.44）、z 序变运行时难题 |
| 程序像素化（高清→降采样量化） | 否决（用户拍板保持高清 cel 风） | demo 可生成但风格断裂，见 output/pixelate_demo.py 死路证据 |
| GPT 直出真像素 | 不采用 | 伪像素风险 + 与现有厚涂资产断裂 |

外观模型沿用 DNF 实证路线：**角色外观 = 职业整图；普通装备隐形只出数值；
武器/时装走"整套重绘 + 调色板变体"**（一稿多色成本≈0），不做通用件拼装。

## 2. 目录结构

```
class_pipeline/
├── README.md                  # 本文档
├── .gitignore                 # 排除 .secret-ui.env / __pycache__
├── .secret-ui.env             # 生图密钥(自包含, 绝不入库)
├── scripts/
│   ├── gpt_client.py          # 生图客户端(自包含; 密钥: 环境变量 > 向上找 .secret-ui.env)
│   ├── common.py              # 公共工具副本: 切片/品红抠底+despill/脚底对齐 (SIZE=256, PIVOT=128,240)
│   ├── gen_all_in_one.py      # Step2 一锅出全动作 sheet(8×8=64格, 每行一动作)
│   ├── gen_row.py             # Step2b 缺格补行(单行 8 格横条)
│   ├── gen_sheets.py          # 备用: 旧链式逐动作生成(27帧×4张, 上/下方向备选)
│   ├── qc_sheet.py            # Step3 QC: 空格检测/行内 IoU/脚底差/行条拼图
│   └── build_class_assets.py  # Step4 切格→抠底→脚底对齐→每动作透明 sheet+manifest
└── swordsman/                 # 每职业一个目录（新职业复制此结构）
    ├── portraits/             # Step0 定稿立绘(两形态: 斗笠/摘笠, 身份锚点)
    │   ├── lihui_hat.png
    │   └── lihui_ponytail.png
    ├── masters/               # Step1 母版(品红底单帧 sprite)
    │   ├── walk_master.png    # 行走 contact 帧
    │   └── attack_master.png  # 劈砍中段帧
    ├── sheets/                # Step2 生成产物(花真金白银, 全部入库)
    │   ├── all_in_one_v1.png          # 64 格全动作一锅出
    │   ├── attack2_row_fix.png        # 缺格补行条
    │   ├── all_in_one_rows.png        # QC 行条拼图
    │   └── qc/                        # QC 报告/放大图
    └── assets/                # Step4 最终资产(build_class_assets 生成)
        ├── walk.png / idle.png / ...   # 每动作 8 格透明底 sheet
        └── manifest.json               # schema=class-assets-v1
```

## 3. 环境事实

- Windows + **PowerShell 7**（Bash 不可用）；Python 3.12+（numpy/Pillow/opencv/pyyaml 已装）。
- 生图 API: 密钥 `class_pipeline/.secret-ui.env`（或环境变量 `GPT_IMAGE_API_KEY`），
  endpoint/model 见 `scripts/gpt_client.py`。价格 ≈ **0.09 元/张，50s/张，无 seed（不可复现）**；
  抽卡预算: 每资产 ×2 取优。
- API 尺寸档: 实测上限 **1536×1536**（传 2048 会被回落）；单行补条用 1536×1024。
- 生成产物是花真金白银的资产，**全部入库**；提交前 `git status --porcelain` 确认
  `.secret-ui.env` 不在暂存区（.gitignore 双保险）。

## 4. 产线流程（六步）

```
Step0 定稿立绘 portraits/（斗笠+摘笠两形态, 身份锚点, 后续所有生成的参考图）
Step1 母版 masters/（透明底单帧 sprite: walk contact 帧 + attack 中段帧;
      由品红母版经探针法重绘转正, 见 §9.2）
Step2 一锅出 scripts/gen_all_in_one.py --transparent
      → sheets/all_in_one_transparent_v<n>.png（64格 8×8, 每行一动作, 真 RGBA 直出免抠图;
      品红链 build_class_assets.py 降级为 fallback, background 参数失败时才启用）
Step3 QC: build_transparent_assets.py 内置 alpha 直读 QC（空格/相邻IoU/循环闭合/脚底差）;
      缺格行 gen_row.py 补行（注意: gen_row 尚未加 --transparent, 需要时先移植）
Step4 资产 scripts/build_transparent_assets.py --sheet <透明sheet>
      → assets/<motion>.png(原生抗锯齿透明底) + manifest.json
Step5 验证: preview.html 逐动作播放目检（帧序列/脚底/循环闭合）
Step6 四方向: left=right 镜像(免费); up/down 各跑一轮
      gen_master_turn.py(转向母版×2) → Step2 --facing up|down → Step4
      --direction up|down → 契约重建(已落地, 见 §9.5)
```

新职业 = 复制 `swordsman/` 目录结构 → 出立绘/母版 → 依次跑 Step2-5。

### Step2 一锅出要点（剑客 pilot 实证）

- **一次生成 64 格、每行一个动作**，同次生成内角色一致性最好（所有帧同源，
  无链式"传话游戏"退化）；实测 7/8 行完整成序列（见 §7）。
- prompt = `PROMPT_HEAD`（总述+角色契约）+ `ROW_LAYOUT`（逐行动作描述），
  两处都在 `gen_all_in_one.py` 里，新职业改这两处即可。
- 抽卡: 效果不行删产物改 `--version` 重跑（幂等: 已存在跳过）。

### Step3 QC 与补行要点

- `qc_sheet.py` 按格**边框环带重估背景色**再抠 mask——品红底有暗角/纹理，
  固定阈值会把暗角判成前景（第一版 QC foot_y 全=191、IoU 虚高 0.99 即此污染）。
- 看三个指标: `empty`（跳格）、`adjacent_IoU`（行内连续性，动作行 0.8+ 合格，
  循环行应先降后升）、`footSpread`（脚底差>8px 属对齐风险，Step4 会兜底）。
- 缺格/跑偏行 → `gen_row.py` 单行补条（8 格横条比 64 格大表更稳，实测一次补成）；
  补行条命名 `<motion>_row_fix_v<n>.png`，Step4 自动整行替换优先采用。

### Step4 资产要点

- 抠底同样走背景重估 + 最大连通域（`build_class_assets.py` 内置，不依赖旧产线）。
- **脚底/水平对齐**: 全帧按 alpha bbox 裁剪 → 最大宽高归一化画布 → 脚底贴同一
  水平线 + 水平中心对齐（帧间重心稳定，播放不抖）。
- **保持原生分辨率不放大**（1536 sheet → cell 192×192，角色有效高约 130px），
  清晰优先；放大策略（NEAREST×1.5 / 生成时要求角色占满格子）待目检后再定。

## 5. 动作与帧数规划（横版 HD-2D, 每行固定 8 格便于切格）

| 行 | 动作 | 帧数 | 播放 | 说明 |
|---|---|---|---|---|
| 1 | walk 行走 | 8 | 循环 | 首尾闭合约束写进 prompt |
| 2 | idle 待机 | 8 | 循环 | 呼吸起伏；旧产线只是借 walk f0，值得单独做 |
| 3 | attack1 挥砍 | 8 | 一次性 | 拔剑过顶→劈下→收势 |
| 4 | attack2 突刺 | 8 | 一次性 | 普攻二段/连招 |
| 5 | death 死亡 | 8 | 一次性 | 末帧躺地停留 |
| 6 | run 跑步 | 8 | 循环 | 无跑步机制的职业可改为待机变体/删行 |
| 7 | hit 受击 | 3+5空 | 一次性 | 快速反馈 |
| 8 | spare 空 | - | - | 预留（技能/骑乘/表情） |

合计 51 帧/方向（不含 spare）；生成侧固定 8 格/行，帧数由 manifest 的 `frames` 字段
声明（客户端/工具按元数据播，不锁 8）。hit 只取前 3 格。

## 6. 关键约定

| 约定 | 内容 |
|---|---|
| sheet 布局 | 恒定 8列×8行(一锅) 或 8列×1行(补行), **透明底(默认, 原生 RGBA)** 或 品红 #ff00ff 底(fallback); 无边框无文字无阴影; cell 内 y 向下 |
| 角色契约 | 所有生成 prompt 必须复述：服装/配色/背剑/葫芦/斗笠/马尾 + "严禁腰间横挂剑鞘"（曾反复跑偏） |
| 母版规格 | 品红底单帧全身, right 向 3/4 视角, walk=contact 姿势, attack=动作中段 |
| 行分配 | 行号即动作（ROW_LAYOUT）, 上=walk 下=spare 固定顺序, 新职业不改顺序只改描述 |
| 循环动作 | walk/idle/run 首尾闭合约束必须写进 prompt 第 1 格 ↔ 第 8 格 |
| 一次性动作 | attack/death/hit 不闭合, manifest `loop:false` |
| manifest | schema=class-assets-v1: motion→{sheet, cols, frames, cell, fps, loop}, 消费方按元数据播 |
| git | 只 add `class_pipeline/` 与 `gpt_sheet_pipeline/`; **.secret-ui.env 永不入库**; 单文件 <100MB |

## 7. 成本账（剑客 pilot 实测）

| 路线 | 生成次数 | 成本 | 一致性 |
|---|---|---|---|
| **一锅出+补行（本产线）** | 1 张 64格 + ≤2 张补行 | **≈0.3 元/方向** | 同源最好；7/8 行完整 |
| 旧链式（27帧×4张/动作） | walk+attack ≈8 张 | ≈0.8 元/2动作 | 链式退化（旧产线 IoU 0.71 教训） |
| 7 动作×4方向全套 | ≈6 张/方向 | ≈1.5 元/方向, 4向 ≈6 元 | — |
| 抽卡预算 ×2 | — | 全套 ≈12 元/职业 | 无 seed, 靠抽 |

## 8. 死路清单（不要再试）

1. **程序像素化**（高清→降采样+量化）: 可生成但用户拍板保持高清 cel 风——
   风格断裂；证据 `gpt_sheet_pipeline/output/pixelate_demo*.py/png`（留档）。
2. **QC 固定品红阈值**: 品红底暗角/纹理会把背景判成前景（foot_y 全=191、
   IoU 虚高 0.99 的教训）——必须按格边框环带重估背景色。
3. **跨动作复用锚点/对齐参数**（继承自旧产线 §7.7）: 每动作/方向独立对齐。
4. **腰间挂剑/剑鞘**: 用户明确否决, prompt 必须带"剑只背在背后、严禁腰间横挂剑鞘"，
   否则稳定跑偏出腰剑。
5. **API 传 2048 尺寸**: 上限 1536, 会被回落——一锅出 cell 192px 是当前现实,
   想要更大格子只能减列数（如 4×8=32 格 cell 384px, 代价是动作分多张）。
6. **抠底只做边缘带 despill 不够**: 品红过渡像素会大片连进前景内部（发梢/衣缘）,
   边缘带处理完仍有粉晕——必须**全局去品红**（r、b 同高且 g 显著低才判定,
   红腰带/流苏等 b 低的红色系衣料不受影响）, 外加 1px alpha 腐蚀吃掉轮廓 halo 环。
   **腐蚀的副作用**: 原本靠细桥连在主体上的脏边碎块会被切成悬空孤岛（角色旁白点）,
   腐蚀后必须二次连通域过滤删碎块（面积阈值 ≥max(25, 0.04%格面积)）。

## 9. 剑客 pilot 实验记录（2026-11-27, 全部入库）

- 定稿立绘: `swordsman/portraits/`（斗笠+摘笠两形态, 参考"逸剑风云决宇文逸"气质原创）。
- 母版: `masters/`（walk contact 帧 + attack 劈砍中段; walk 第一抽剑在手, 重抽修正背剑）。
- 一锅出: `sheets/all_in_one_v1.png` — walk/idle/attack1/death/run/hit 六行动作
  完整（death 8 帧后仰→踉跄→倒地→躺平全程连贯）; attack2 行 c3 跳格+c5 跑偏。
- 补行: `sheets/attack2_row_fix.png` — 单行 8 格突刺一次补成（含逐格姿势 prompt）。
- QC: `sheets/qc/` 行条图+放大图; 行条目检确认为准（QC 数字 v1 被暗角污染不可信,
  qc_sheet.py v2 已修）。
- commit: 8225eca（pilot 实验）→ 本目录重构（独立产线化）。

### 9.1 闭环补全（2026-11-27 下午, 契约导出 + Step5 + 法线移植）

- **契约导出** `scripts/export_client_contract.py` → `swordsman/client_contract/`:
  crescent-traveler v1 同契约（character.json + right/{animation.json,atlas.png,frames/}）,
  帧 256×256 重锚定（脚底 y=240 / 中心 x=128, 旧产线 fit_canvas 同规格）,
  全动作共享 96 色 MEDIANCUT 色板; walk 作 drop-in clip, 全动作在 `motions/` 扩展键
  （character.json "motions" 为扩展, 客户端忽略未知键, 多 clip 支持待客户端立项）。
- **QC 数字**: walk 循环闭合 0.955 / idle 0.974 / attack1 0.94 / attack2 相邻
  min 0.063（突刺大位移, 逐帧目检为合理快变非撕裂）/ death 首尾 0.066（站→躺, 预期）
  / **run 首尾 0.557 偏低**——f7 相位与 f0 不接, 待补行（TODO#1）。
- **Step5 播放验证** `preview.html`（自包含 canvas2d 播放器: 动作切换/逐帧 scrub/
  洋葱皮/脚底线/URL 参数）: walk 循环、attack 弧线、death 落地全部目检通过。
  过程中抓出并修复 **halo 缺陷**（见 §8.6: 全局去品红 + 1px 腐蚀, v3 已进
  build_class_assets.py, 修复后发梢/披风边缘干净、红腰带无误伤）。
- **法线移植** `scripts/normals.py`（自包含版: 直接吃透明底 RGBA）+ 首版
  `swordsman/geometry.yaml`（归一化空间手写标注）: 背刀刃 metal mask 命中准确,
  斗笠/躯干/腿方向明暗成立; 发梢/手臂管件待目检迭代。

### 9.2 透明底探针（2026-11-27, 推翻产线根基假设）

`scripts/probe_transparent.py` 用 `background=transparent` + `output_format=png`
实测 proxy 的 gpt-image-2: **支持透明直出**。HTTP 200, 返回真 RGBA
（全透明 73.6% / 不透明 24.9% / 半透明 1.4% 真抗锯齿边）, 无棋盘格
（透明区亮度 0.2）, 无品红, 角色保真完整。产物 `sheets/transparent_probe/`。

结论: 品红+抠图链建立时假设"API 出不了透明底"——**该假设未经验证且已被证伪**。
透明直出可消掉 matte/despill/腐蚀/清岛整条链。切换前待验证:
①透明底 64 格一锅出的一致性与 QC 兼容性 ②1536 大图下参数稳定性 ③多轮抽卡表现。
在上述验证通过前, 品红链保持现役; 通过后透明直出转正、品红降级 fallback。


### 9.3 透明直出转正（2026-11-27 晚, 64 格一锅验证通过）

透明底 64 格一锅出 ×2 抽卡（各 0.09 元）实测对比:

| 指标 | 品红链(旧) | 透明直出 v1(新, 已转正) |
|---|---|---|
| 空格 | attack2 c3 跳格, 需补行 +1 张 | **零空格, 7 动作一次全成** |
| attack2 行内 IoU | 0.39~0.41 | **0.833** |
| run 循环闭合 | 0.557(老大难) | **0.681** |
| 边缘质量 | 抠图三道工序仍留 halo/白点隐患 | **原生抗锯齿, halo/白点类 bug 从根上消失** |
| 工序 | matte→despill→腐蚀→清岛 | alpha<10 归零 + 清孤岛两步 |

v1 转正为现役资产（assets/ + client_contract/ 已全量重建, preview 复验通过）;
v2 留档为抽卡对照。品红产物（all_in_one_v1.png / attack2_row_fix.png / 行条 / qc/
/ 品红母版）已删除, git 历史可考。品红链代码（build_class_assets.py / qc_sheet.py
/ gen_row.py）保留为 fallback, **gen_row.py 尚未加 --transparent, 补行前需先移植**。

### 9.4 法线标注迭代 + load_frame 底型 bug 修复（2026-11-27 晚）

目检 v1 法线渲染发现两类问题, 顺藤摸瓜修出一个产线级 bug:

- **load_frame 底型误判(bug)**: 旧判断 `alpha.max() < 250` 把含不透明像素的
  透明资产帧误判为品红底 → chroma key 把透明区的黑 RGB 当前景色 →
  **全图前景, silhouette 失效**, 法线场实际是全图缓变场(v1 的"立体感"是假象),
  metal 高光条才会横穿脸前。修复: 改 `alpha.min() < 250`(透明帧必有 alpha=0 区)。
- **geometry v1 标注整体错位**: v1 按旧品红母版手标, 对透明 v1 资产帧系统性
  偏高 12~45px, 且刀刃 poly 横穿躯干(背剑设定下剑身应被身体遮挡)。

迭代方法固化为闭环工具链: **行带 alpha 分析(每 10px 扫内容 x 段)定位部件 →
`scripts/geometry_preview.py` 部件叠加目检 → 数值化贴合率检查(mask 内 alpha
覆盖率, 主要部件≥0.7) → normals.py 重渲染目检**。

- `geometry.yaml` v2.2(站姿/walk/idle 通用): 全部件按修复后空间重标;
  刀刃 poly 收缩为柄头可见小块; 新增披风部件。贴合率: 后臂/头脸 1.0,
  躯干 0.98, 马尾 0.82, 腿/斗笠 0.67~0.82。
- `geometry_attack.yaml` 新增(attack 专用, 姿态差异大): 低伏弓步+举剑劈砍
  专用标注, 剑刃 poly 按实测斜线 (168,115)→(196,193) 重标。贴合率: 后臂 1.0,
  头脸 0.97, 躯干 0.87, 腿 0.73~0.75。
- 复渲染验证: light-top 穿脸白条消失, 金属高光只在柄头/刃带, 左右受光
  差异清晰(light-left 披风面亮 / light-right 胸面+刃亮)。

用法: `python normals.py <帧> swordsman/geometry.yaml <out>`(站姿帧) /
`python normals.py <帧> swordsman/geometry_attack.yaml <out>`(攻击帧);
预览: `python scripts/geometry_preview.py <帧> <geometry.yaml> <out.png>`。

### 9.5 四方向扩展（2026-11-27 深夜, right/up/down 三方向落地）

成本 0.54 元（转向母版 ×4 各 0.09 + 一锅 ×2 各 0.09）:

- **转向母版** `scripts/gen_master_turn.py`: 从 right 透明母版生成
  up(背面)/down(正面) 同姿势母版, 身份/配色/背剑设定全保真
  （背面版剑身轮廓完整可见; attack 转向版姿势锚弱化为站姿, 靠一锅行描述补）。
- **一锅出** `gen_all_in_one.py --facing right/up/down`: PROMPT_HEAD 朝向词按
  FACING_TEXT 替换, 输出 `all_in_one_transparent_<facing>_v<n>.png`。
- **QC: 三方向 ×7 行全部零空格**（连续 3 次 64 格零空格, 透明直出稳定性确立）:
  | 方向 | walk(loop) | idle | attack1 | attack2 | death | run(loop) |
  |---|---|---|---|---|---|---|
  | up | 0.837(0.874) | 0.929 | 0.651 | 0.743 | 0.702 | 0.792(0.665) |
  | down | 0.901(0.898) | 0.927 | 0.663 | 0.671 | 0.585 | 0.690(0.623) |
  up walk 循环 0.874 反超 right(0.722); down attack1/attack2 loop 0.956/0.959
  (一次性动作首尾回站姿)。down 小瑕疵: attack1 f3 剑形糊/死亡 f1 张臂,
  契约 256 尺寸下弱化, 可后续 gen_row 补行（待 --facing）。
- **资产/契约 v2**: `build_transparent_assets.py --direction` → assets/<dir>/ +
  manifest class-assets-v2(directions.<d> 聚合, v1 扁平自动迁移); 
  `export_client_contract.py` 多方向导出——每方向 walk drop-in(`<d>/`) +
  motions/(right 布局零破坏) + motions/<d>/, 跨方向共享 96 色板;
  character.json v2: directions.{right,up,down}.idle_frame 各自独立。
- **preview.html 方向切换**: right/up/down 按钮组 + `?direction=` 参数,
  浏览器终验 up/attack2 f5 与 down/walk 播放全部干净（无 halo/白点）。
## 10. 风格基准与渲染配方（2026-11-27 拍板, 假像素路线）

### 10.1 客户端渲染事实（hd2d-mmo 实测源码）

- 角色 = Sprite3D billboard + **TEXTURE_FILTER_NEAREST**（裸 nearest 无 mipmaps,
  `pixel_actor.gd:53`, 且有测试断言锁定该行为）; 环境卡用 NEAREST_WITH_MIPMAPS。
- 视口 1920×1080 无低清视口; 日常取景角色屏显 **~110px 高**, 512px 源帧被最近邻
  缩小丢弃约 80% 采样 → 硬边阶梯 = **"高清带像素感"（假像素）**, 是设计选择非 bug。
- 3D 相机带景深(DOF), 精灵随远近会被景深虚化——观感与逸剑同源, 但我们源图精度高。

### 10.2 真像素对标（逸剑风云决实证, UE4 真像素 + 3D 场景）

| 维度 | 真像素（逸剑 ~50px 精灵） | 假像素（本产线 高清厚涂+nearest 缩小） |
|---|---|---|
| 拉近镜头 | **立即崩**（像素块放大）→ 对话只能切高清立绘双资产 | 优雅退化到厚涂原画精度, crescent 有 ~4.6× 余量 |
| 拉远镜头 | 无损但颗粒粗 | 颗粒变细, 与 nearest 环境卡质感统一 |
| 精灵清晰度 | 糊（密度失配+AA 糊+DOF 三重叠加）, **全靠立绘撑观感** | 精灵本身即主视觉, 衣纹/明断保留厚涂信息 |
| 立绘-精灵关系 | 两次创作, 风格断裂 | 同母版同锚点一次生成, 风格零断层 |
| 生成侧 | GPT 画不了真像素（§8 死路） | GPT 天然擅长厚涂 cel, 像素感渲染侧白送 |

### 10.3 风格基准（一句话）

**精灵保真度对标"立绘缩小的下限", 不对标"真像素的上限"**——精灵和立绘同源,
走近是厚涂、拉远是细像素, 同一张画; 相机远近是风格旋钮（颗粒密度可滑）,
这是真像素做不到的自由度。

### 10.4 边界条件（产线规则由此而来）

1. **拉近端余量不均等**: crescent 512px 源 ≈4.6× 余量; 本产线 cell 192px（有效高
   ~130px）仅 ~1.4×——日常走场够用, **特写必须大格子重生成, 不许放大 192**（见 TODO#3）。
2. **拉远端**: 角色裸 nearest 无 mipmaps, 静止干净、跑动远景可能有 1px 边缘爬行;
   真遇到是客户端一行配置的事（NEAREST_WITH_MIPMAPS）, 不归本产线管但记录在案。
3. **像素感是渲染侧赠品**: 生成 prompt 永远只管厚涂 cel 质量, 不要试图画像素。

## 11. TODO（接手从这里开始）

1. **run 行循环闭合**（可选优化）: 透明 reroll 已从 0.557 改善到 0.681（契约口径
   0.584）; `gen_row.py --transparent` 已就绪, 需要时直接出 run 透明补行条
   （build_transparent_assets 会自动整行替换）。
2. Step5 播放验证已完成（2026-11-27, 见 §9.1; 顺带修复 halo 缺陷, 见 §8.6）。
3. 放大策略拍板: **特写场景用大格子重生成（4 列×8 行 → cell 384px, 代价是动作分
   多张）, 禁止放大 192 原生图**; 日常走场维持原生 192（屏显 ~110px, 1.4× 余量够用）。
4. ~~四方向~~ **已完成**（2026-11-27, 见 §9.5）: right/up/down 契约 v2 全落地;
   遗留: `gen_row.py` 补 `--facing`（up/down 缺格补行前置）。
5. 第二职业复制本流程验证产线可复制性。
6. ~~契约对齐~~ **已完成 + 多 clip 立项文档已出**（`docs/multi_clip_proposal.md`）;
   下一步客户端侧立项: 多 clip 播放器（motions/ + clip_meta 扩展键已就位）。
