# AI 协作工作手册 — gpt_sheet_pipeline

> 给新加入的 AI/开发者: 先读完本文档再动手, 可避免重走所有已验证的死路。
> 最后更新: 2026-11-26 · 维护者: lff2116788383 + Doubao 协作会话

## 1. 项目定位与边界（最重要）

- 本仓库 `h3-character-studio` 是 fork 自 `winkidney/h3-character-studio`（upstream）的 H3 视频模型产线项目。
- **`gpt_sheet_pipeline/` 是我们自己的独立补充方案**（GPT 生图替代 H3 做逐帧精灵），与 upstream 无关。
- **所有改动只允许进 `gpt_sheet_pipeline/`**，不碰仓库其他任何文件——保证与 upstream 永不冲突。
- `E:\work\hd2d-mmo\client` 是目标游戏客户端（Godot 4, HD-2D）。**验证阶段绝不修改客户端**；
  所有渲染验证在本目录 `prototype/`（three.js）完成。
- 传奇渲染结构参考本地 `E:\work\game\mir2x`（C++ 引擎，用户自己的项目）——分层/z 序表/逐帧偏移的祖师爷。

## 2. 环境事实

- Windows + **PowerShell 7**（Bash 不可用）；多行内容用 Write 工具写文件，别用 here-string 包装。
- Python 3.13 + numpy / Pillow / opencv-python-headless / pyyaml / requests（已装）。
- 生图 API: 密钥在 `gpt_sheet_pipeline/.secret-ui.env`（**绝不入库**），endpoint/model 见 `gpt_client.py`。
  价格 ≈ **0.09 元/张，50s/张，无 seed（不可复现，靠抽卡）**。抽卡预算: 每资产 ×2 取优。
- 本地服务: `cd prototype && python serve.py 8765` → http://127.0.0.1:8765/index.html（支持 URL 参数组合）。
  Windows 注册表会把 `.js` 映射成 `text/plain`，浏览器因此拒绝加载 ES module；`serve.py` 已内置 MIME 修正，勿删。

## 3. 资产产线（已跑通的路径）

```
母版 PNG(任一方向)
  → gen_sheets.py      4×2 sheet (1024×1024, cell=256×512, 品红 #ff00ff 底)
                       27帧 = 4张链式(母版+上一张), 末张带首尾闭合约束
  → common.py          slice_sheet → matte_cell(品红抠底+despill) → fit_canvas(脚底 pivot 128,240)
  → build_character.py 全方向共享 96 色板 → atlas(8列2px gutter) + animation.json + character.json
                       (对齐 hd2d-mmo crescent-traveler 契约, 可直接拷进客户端)
  → normals.py         解析法线+金属蒙版+四向受光 (与生成器解耦, 需人工 geometry.yaml 标注)
```

## 4. 关键约定（改代码前必读）

| 约定 | 内容 |
|---|---|
| sheet 布局 | 恒定 4列×2行, 品红底, 无边框无文字无阴影; cell 内坐标 **y 向下** |
| 锚点 schema | `anchors.json` 每帧 `wrist_r/elbow_r/ankle_a/ankle_b/head_top`, cell 内像素坐标 |
| weaponOrder | mir2x 式逐帧表: **1=画在身体后面, 0=身前**; walk 全 0, attack=[0,0,1,1,0,0,0,0] |
| 武器单图 | 竖直、刃朝上、握把=图片底部中心; 挂载=握把贴 wrist_r, 刀刃方向=肘→腕延长线 |
| 单图部件挂点 | pivot=底部中心(斗笠等), 挂 head_top/wrist_r; three.js 里 geometry.translate(0,+h/2,0) |
| 服装偏移校正 | 服装 sheet 对素体 sheet 的全局偏移用**头顶+脚线双基准取中位**; 别用质心(袍子质量会带偏 20px+) |
| 攻击动作 | 空手画(刀后续挂载); 提示词让手臂"过顶→前伸→低收"的劈砍弧; 空手时模型易画成冲拳, 弧线可接受 |

## 5. 实验方法论（每轮验证都这么干）

1. **一个实验 = 一个可复跑的 py 脚本**（幂等: 已存在的生成物跳过），产物进 `output/<实验名>/`。
2. 生成 ×2 抽卡，QC 指标自动选优: sheet 内相邻帧 IoU、循环闭合 IoU、光流中位、配准误差。
3. **指标 + 目检双确认**: 任何结论必须有数字 + 截图（网格版图用于人工标注）。
4. 浏览器验证用 URL 参数固定状态: `?motion=attack&weapon=1&cloth=B&hat=1&paused=1&frame=4&anchors=1`。
   注意: 连续快速导航会触发浏览器 WebGL context 保护（白屏），等几秒重开即可，不是代码问题。
5. 每个否定结论也要留证据（见死路清单），防止后续会话重走。

## 6. 已验证结论（数字为准）

| 结论 | 指标 |
|---|---|
| sheet 方案 vs 逐帧独立 | 相邻 IoU 0.80~0.85 vs 0.739; 质心漂移 ±2px vs 40px |
| 锚点引导整套生成(衣服含身体) | 合成 IoU **0.94~0.96** |
| 武器单图+锚点旋转挂载 | 构造上零漂移; 浏览器实测 walk/attack 全帧跟手 |
| weaponOrder z 序切换 | 原型实测起手帧刀在身后(1)、劈下在身前(0) |
| 素体身份锚点 | 脱衣后脸/辫子/头饰保持, QC 0.85+; 配准光流中位 0.87~2.23px |
| 斗笠 head_top 挂载 | 首版误用 attack 标定→walk 全帧浮空 25px+双动作偏左 19px; 实测重标 attack[125,100]/walk[122,73]系 后帽沿压发带 |
| 三轮否决: 空心大件分层 | 无形人台 0.795 / 空心+锚点 0.78 — **GPT 画不准没有身体的衣服** |
| 混合分层资源账 | 10衣×10武×3发型=600搭配 → 23 件资源 ≈15 元 vs 预生成 840 元/1.9GB |

## 7. 死路清单（不要再试）

1. 逐帧独立生成（漂移 40px）与链式逐帧参考（IoU 0.710 + 传话游戏退化）
2. GPT 直接画法线（不可验证）; 法线走 `normals.py` 确定性解析
3. 空心/无形人台大件部件（两轮封顶 0.78, 动幅弱）
4. diff 提取服装层（边缘污染 73%）→ 已被"武器单图+锚点"和"整套锚点引导"取代
5. 质心做 sheet 对齐基准（被袍子质量带偏）; 用头脚双基准
6. H3 本机跑（Windows+RTX3070 不满足 Linux/CUDA13）; H3 产线走云端 `--url`
7. **跨动作/跨方向复用同一套锚点标定**——walk 与 attack 素体是不同生成批次, 头冠线在 cell 内
   相差 26px, 真实头中心 x≈125.5; 锚点表必须逐动作×方向从素体像素实测, 上原型前先做逐帧接触模拟

## 8. 方案文档与原型

- 换装系统完整方案（架构/资源账/落地步骤）: `docs/hd2d-equipment-swap-plan.md`
- three.js 原型: `prototype/index.html` + `prototype_data.json`（由 `build_prototype_assets.py` 生成）
- **纸娃娃绑定导出工具**: `prototype/tool.html`（资产库筛选/拖拽绑定/单帧微调/工程 ZIP 分享/客户端 ZIP 导出），
  用法与实测见 `docs/paperdoll-tool.md`；`index.html?edit=1` 为其轻量锚点校准前身。
- 运行: `cd prototype && python serve.py 8765`
- 已实测组合: walk+刀(挂载✓), attack起手+绿袍(z序身后✓), attack劈下+绿袍+斗笠(挂载✓)
- 斗笠挂载复验（2026-11-26, 两轮）:
  - 第一轮只验 attack f4 即判"通过"——**误判**; 用户抽查 walk 帧当场抓出浮空。复验必须逐动作逐帧, 不能只看单帧。
  - 像素级复测: walk 与 attack 素体头冠线相差 26px(walk 51 / attack 77), 真实头中心 x≈125.5;
    首版锚点共用 y≈96-100 / x≈102-108 → walk 全帧浮空 24~27px、双动作整体偏左 ~19px。
  - 修正: attack head_top x→125(居中, y=100 不变); walk 重标 [122,73]系(头冠线+attack 校准 δ=22)。
    浏览器复验 walk f0/f4 + attack f4, 帽沿均压住头顶发带, 无浮空。
  - A/B 证据: `images/debug-hat-walk-f4.png`(现状 vs 修正)、`images/debug-hat-attack-x.png`(x=106 vs 125);
    终态对照: ![斗笠落位对照](images/hat-mount-check.png), 全身 `images/hat-on-full.png`、
    walk `images/hat-walk-f0.png`、`images/hat-walk-f4.png`。
- 锚点调试十字曾被衣服/头饰盖住(不透明线材质在不透明队列先画): 已改为 transparent+renderOrder=10,
  现在十字始终盖在最上层。
- 产物截图: 会话记录; 组合自查用 URL 参数

## 9. Git 红线

- 只 add `gpt_sheet_pipeline/`; 提交前 `git status` 确认 **`.secret-ui.env` 不在暂存区**。
- `output/`（测试资产, ≈40MB）与 `prototype/assets/` 均入库——这是抽卡花真金白银的产物。
- 单文件 >100MB 禁止（GitHub 硬限）; 当前最大单文件 ≈2MB, 安全。
- 提交信息: `feat(gpt_sheet_pipeline): <内容>` 英文正文, 与仓库既有风格一致。

## 10. 当前待办（接手从这里开始）

1. ~~**斗笠 head_top 复验**~~ ✅ 2026-11-26 两轮完成: 第一轮只验 attack 即判通过属误判, 用户抽查
   walk 抓出浮空; 复测后 attack x→125、walk 重标 [122,73]系, 浏览器复验 walk f0/f4 + attack f4 全部贴合。
   详见 §8 与 §7.7 教训。
2. 四方向扩展: 当前全部只有 right 向; 量产需 ×4 方向。成本评估与分阶段方案见
   `docs/four-direction-expansion-plan.md`（评估稿, 待拍板, 先 Phase 1 四向试点再量产）。
   注意 §7.7: 四向锚点全部要逐方向实测。
3. 素体赤足化: 攻击帧素体布鞋从袍下露出（body 与 cloth 脚部姿势差）, 素体宜赤足/最小鞋。
4. 服装A/B 的 walk 服装对素体偏移 1~2px, attack 0~2px — 已在 clothOffset 校正, 无需再调。
5. 客户端接入（另行立项, 需用户拍板才可动 hd2d-mmo）: 衣服 clips 切换 + 小件锚点 Sprite3D。
6. despill 紫边: 素体/服装/斗笠边缘有粉紫色 halo（matte 残留, 截图可见）, 需强化 despill 或
   边缘 1px 腐蚀; 动 `common.py` 前先做前后 A/B, 别悄悄改影响全部存量资产。
7. walk 与 attack 素体未共配准（头冠线差 26px、脚底对齐但头顶高度不一致）: 量产前在
   `build_prototype_assets.py`/`build_character.py` 里统一按头顶+脚线双基准对齐, 否则跨动作小件锚点都要另标。
8. ~~**锚点人工校准闭环的构建侧接入**~~ ✅ 2026-11-26:
   `prototype/index.html?edit=1` 导出 `anchors_manual.json`（schema=anchors-manual-v1，稀疏覆盖）；
   纸娃娃工具导出 `bindings.json`（schema=paperdoll-bindings-v1，全帧热区轨迹）。
   用法: 分别复制为 `output/anchors_manual.json` / `output/paperdoll_bindings.json` 后运行
   `build_prototype_assets.py`；**人工标定优先于脚本标定**，anchors_manual 优先级最高。
   文件不存在则原流程零变化；schema/动作/帧号/锚点非法会明确报错。
   已测: 临时目录双 schema 单测 + 真实构建 walk#4 [122,73]→[122,46]→恢复 [122,73]，重建产物无 diff。
9. ~~纸娃娃工具一期+二期~~ ✅ 2026-11-26: `prototype/tool.html`（文档 `docs/paperdoll-tool.md`）。
   一期: 资产库筛选/拖拽绑定/单帧微调/客户端 ZIP 导出; 二期: 3D 场景缩放演示(billboard/透视相机);
   工程 ZIP 保存/分享（paperdoll-project-v1, 资产+绑定+热区+设置整包带走）、
   衣服跨动作成组绑定（同名姊妹资产自动成组+应用全部动作按钮）已交付。
   后续: 多方向批量。

