# gpt_sheet_pipeline — GPT 生图主角产线

用 gpt-image-2 一次性 sprite sheet 生成行走循环帧，经确定性后处理产出
**hd2d-mmo 主角规格**资产（与 h3-character-studio 产线产物同契约）。

实测数据（见 `docs` 与会话记录）：sheet 方案相邻帧 IoU 0.80~0.85、描边抖动
0.6%~0.95%、质心横向漂移 ±2~3px，显著优于逐帧独立生成（IoU 0.739 / 漂移 40px）。

## 流程

```
母版 PNG (任一方向, 768+)
   ↓ gen_sheets.py: 4×2 sheet × N 张（27帧=4张, 链式参考: 母版+上一张sheet）
   ↓ 末张自动带首尾闭合约束（引用第一张 sheet 的首格姿态）
   ↓ build_character.py:
      切片 → 品红抠底+描边去污染(despill) → 全方向共享 96 色板量化
      → 256 画布脚底对齐 pivot(128,240) → atlas + animation.json + report.json
      → character.json（hd2d-mmo / h3-character-studio 同 schema）
```

## 使用

```sh
# 0. 密钥: 环境变量 GPT_IMAGE_API_KEY 或本目录 .secret-ui.env
cp config.template.yaml config.yaml   # 改 id / directions / master 路径

# 1. 一键跑一个方向（生成 4 张 sheet ≈ 4×50s + 构建秒级）
python run_pipeline.py --config config.yaml --direction right

# 2. 只生成不构建 / 只构建不生成
python gen_sheets.py --master ../examples/jade-traveler/masters/right.png --direction right --sheets 4
python build_character.py --config config.yaml --directions right
```

产出（对齐 crescent-traveler 契约，可直接复制进 `hd2d-mmo/client/assets/characters/`）：

```
output/character/
├── character.json            # generation: "gpt-sheet", review: pending
└── right/
    ├── animation.json        # 27帧 manifest, 逐帧 sha256 + duration_ms
    ├── atlas.png             # 8列网格, 2px gutter（与 h3 产线同规格）
    ├── report.json           # QC 指标 + provenance + warnings
    └── frames/00000.png...
```

## 抽卡工作流（建议）

1. `run_pipeline.py` 跑一个方向 → 看 `report.json` 的 QC 指标 + `frames/` 目检
2. 不满意 → 删掉对应 `sheet-XX.png` 重跑 `run_pipeline.py --skip-gen` 之外的生成步骤
   （gen_sheets.py 幂等跳过已存在的 sheet，删哪张重抽哪张，链式参考自动重算）
3. 整方向满意后再跑下一方向（四方向共享色板在 build 时统一生成）
4. 全方向冻结后才做下游（法线/材质逐帧标注）——sheet 每次重画会全量重渲染，
   提前做下游会被重抽作废

## 换装系统验证（锚点分层，方案见 `docs/hd2d-equipment-swap-plan.md`）

MMO 的时装换装不能靠"每个搭配整套重生成"（N×M×K 乘法爆炸），本目录的脚本验证了
**锚点骨架 + 混合分层**方案：小件单图挂锚点、大件锚点引导整套生成。

| 脚本 | 作用 |
|---|---|
| `make_anchors.py` | 手工标注素体 8 帧关键点（腕/肘/踝），产出 `output/swap_parts/anchors.json` + 带彩色十字的锚点参照 sheet |
| `swap_test.py` | 换装可行性：素体 / 服装A / 服装B 三 sheet，QC + 光流配准 + diff 层提取 |
| `swap_parts_test.py` | 无形人台（空心服装）部件生成 + diff 层对照 |
| `swap_parts_cal.py` | sheet 级全局偏移校准（一次平移吃掉约 95% 对齐收益） |
| `anchor_swap_test.py` | **核心验证**：武器单图 + 锚点旋转（逐帧跟手）+ 锚点引导整套生成（合成 IoU 0.94~0.96） |
| `anchor_hollow_test.py` | 空心 + 锚点部件（0.77~0.78，证明大件不能脱离身体） |
| `compose_compare.py` | 原版帧 vs GPT 帧同位几何标注的同光照法线对比 |
| `normals.py` | 解析法线 + 金属蒙版 + 四向受光预览（与生成器解耦，GPT/H3/手绘帧通用） |

实验结论（2026-11-26）：**小件分层成立**（武器单图 0.09 元/件，锚点变换零漂移，全角色复用）；
**大件分层否决**（空心部件两轮封顶 IoU 0.78，无身体则 GPT 摆不准且动幅弱）；
**锚点引导整套生成成立**（0.94~0.96，姿态/动幅/位置全对齐）。最终架构为混合分层。

实验产物在 `output/{swap,swap_parts,anchor_swap,anchor_hollow}/`（不入库，含 metrics.json 与预览图）。

## 已知限制（实测）

- sheet 相位为近似执行：8 格是大致步态相位，非严格 biomechanics 序列；
  每方向 27 帧由 4 张 sheet 拼接，sheet 间仍是独立采样（链式参考缓解）
- 循环闭合依赖末张的闭合提示词，`report.json` 的 `loop_closure_iou` 用于验收
- 描边可能有少量品红残留（despill 已处理大部分，顽固残留需人工修帧）
- gpt-image 接口无 seed 参数，同提示词不可复现（成本 9 分/张，靠抽卡）
- 法线/材质不在自动生成环节：需人工几何标注（`normals.py` 的 geometry.yaml，
  单帧 30 分钟级），但一旦标注完成，法线合成与受光预览是全确定的
