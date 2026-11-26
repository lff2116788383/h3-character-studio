# 纸娃娃绑定导出工具（paperdoll-tool）

位置：`prototype/tool.html`（纯前端单页，无构建、无外部依赖；ZIP 为内置 stored 打包器）。

定位：把「脚本标定锚点 → 重建 → 看效果」的闭环，改成
**资产库拖拽绑定 → 自动播放校验 → 单帧微调 → 一键导出客户端产物**。
参考 RPG Maker 角色生成器布局、PixelDoll(MIT) 的分层同 pivot/zip 思想、TDSM 的尺寸导出面板；
不引入 PixelLab/AI 生成管线，不使用 GPL 代码或许可证混合的 LPC 素材。

## 快速开始

```powershell
cd gpt_sheet_pipeline/prototype
python serve.py 8765
# 浏览器打开 http://127.0.0.1:8765/tool.html
```

- 内置资产：walk/attack 素体、服装 A/B（各两动作）、斗笠、直刀。
- 左侧资产库：`＋导入图片`（PNG/WebP，可多选）→ 按文件名预判类型（hat/斗笠→头盔，sword/刀→武器…），
  类型/标签/序列列数/帧数可在右侧改。支持部位筛选 chips、搜索、只看已绑定。
- 自定义资产与工程（绑定、热区、导出设置）存 IndexedDB，刷新/重开不丢；内置资产不入库。

## 绑定模型（刻意保持简单）

- **拖拽绑定**：把卡片拖到角色上。头盔/武器自动绑到默认热区（头顶/手腕），落点即挂点偏移；
  衣服为整格层，只需全局偏移；素体卡片拖入=设为当前动作素体（热区自动粗估，需校准）。
- **自动校验**：绑定后自动播放当前动作。武器朝向默认跟随「肘→腕」方向，可改固定角度。
- **单帧微调**：暂停在某帧，直接拖动画布上的装备 → 只记录该帧修正 `fix[frame]`；
  全局偏移/缩放在右侧面板改。可清除本帧/全部修正。
- **热区编辑**：开启「显示/编辑热区」后拖动彩点编辑当前帧；「本帧→全部帧」用于静态或新导入素体。
- **衣服成组绑定**：拖入带动作词的服装（如「服装A walk」）会自动找同名姊妹资产（「服装A attack」）一并绑定，
  槽位标签显示实际绑定的动作（walk+attack）。名称不含动作词、或同一件衣服通用于所有动作时，
  在衣服槽面板用「应用到全部动作」；「只留当前动作」撤销成组。
- **多方向批量**：底栏「方向」切换 right/left/up/down，每方向独立的素体引用、绑定与热区轨迹。
  内置资产只有 right；其他方向导入图片后「设为当前动作素体」开始，可用「从right复制绑定」
  把已校准绑定复制过来作起点（各方向锚点不同，需逐帧微调），「清空方向」重置当前方向。
  导出客户端 ZIP 时自动打包所有有素体的方向。

## 导出（客户端契约）

底部「导出客户端 ZIP」导出**当前动作**，目录与 `build_character.py` / hd2d-mmo client 对齐：

```
<id>/<version>/
├── character.json            # size/pivot/pixel_size/directions.<dir>/idle_frame（所有已导方向）
├── right/
│   ├── atlas.png             # 8列(可改)+gutter 2+margin 1；region 与客户端 AtlasTexture 对齐
│   ├── animation.json        # frames[].region/visible_bounds/duration_ms/sha256/source
│   ├── frames/00000.png…     # 逐帧底账
│   └── bindings.json         # 该方向槽位绑定+单帧修正+热区轨迹（回灌产线用）
├── left/ …                   # 其余有素体的方向同构；无素体的方向不导出
└── README.txt
```

帧规范化复刻 `common.fit_canvas`：alpha bbox 裁切 → 最长边≤248 等比 → 脚底对 pivot(128,240)、水平居中；
**另加防裁顶约束 nh≤pivotY、nw≤outW**（修复首版斗笠顶部被裁 8px 的问题）。
`review` 固定 `pending`：进客户端前仍需逐帧人工复核。

## 实测记录（2026-11-26，浏览器）

- 拖放绑定：斗笠→头顶、直刀→手腕、服装B walk→衣服槽，合成落位正确；
- 单帧修正：暂停拖斗笠 → `bindings.headwear.fix={"0":{dx:3,dy:-12}}` 精确落盘；
- 持久化：刷新后三槽绑定与导出设置仍在；
- 导入：`hat_rgba.png` → 自动识别 headwear，卡片 8→9，删除后回到 8；console 无错误；
- 导出 ZIP：`zipfile.testzip()` 通过；8 帧 256×256，atlas **2064×258**（与 GPT 产线一致），
  region0 `[1,1,256,256]`，duration 42ms，idle_frame=5；证据 `images/tool-export-frame0.png`。

## 3D 演示（二期已交付）

底部「3D 演示」打开悬浮视窗（懒加载现有 `vendor/three.module.js`）：

- 当前动作的合成帧按导出规范化后作为精灵贴图，**pivot 脚底落地**，地面网格+坐标轴+透视相机；
- 滚轮缩放、拖动旋转视角、「面向相机」billboard 开关、复位；
- 播放/逐帧/改绑定/改热区会同步刷新 3D 贴图（与 2D 画布同源）。
- 基础 unlit 贴图演示；客户端的逐帧法线受光不在此复刻。

## 回灌产线（已接通）

纸娃娃 ZIP 中对应方向子目录的 `bindings.json`（如 `right/bindings.json`）可复制为
`gpt_sheet_pipeline/output/paperdoll_bindings.json`，
再运行 `build_prototype_assets.py`，其 `anchors` 热区轨迹会覆盖脚本标定并重建 `prototype_data.json`。
`index.html?edit=1` 导出的稀疏锚点则放 `output/anchors_manual.json`；两者同时存在时后者优先。
文件不存在时构建流程不变。非法 schema/动作/帧号/锚点会直接报错，不会静默写坏数据。

## 工程 ZIP 保存 / 分享

底部「保存工程 / 打开工程」，把编辑现场整体带走（换机/换浏览器可续）：

```
project.zip
├── project.json          # schema=paperdoll-project-v2：导出设置、各方向素体引用、
│                         # 槽位绑定+单帧修正+热区轨迹、自定义资产清单（兼容导入 v1）
├── assets/<id>.png       # 自定义资产原图（内置资产不入包，导入端自动重建）
└── README.txt
```

- **保存工程**：当前所有自定义资产 + 绑定/热区/导出设置一键打包，文件名 `<id>-<version>-project.zip`。
- **打开工程**：内置 ZIP 读取器（stored + deflate-raw，CRC32 校验）解析后恢复现场；
  同 id 资产幂等跳过，缺失引用的绑定自动丢弃，不污染现有工程；
  客户端产物 ZIP 没有 `project.json`，会被明确拒绝而不是静默导入。
- 注意工程 ZIP 与客户端产物 ZIP 是两种东西：前者给工具续编，后者给客户端/回灌产线。

## 边界与下一步

- 一期 2D 绑定+导出、二期 3D 场景缩放演示均已交付；热区回灌产线已接通；工程 ZIP 保存/分享已交付；
  衣服跨动作成组绑定已交付；多方向批量（方向切换/每方向绑定/全方向导出）已交付。
- 四方向资产的 GPT 生图量产（成本与阶段见 `docs/four-direction-expansion-plan.md`）仍待拍板。
- 不修改 hd2d-mmo 客户端；产物拷贝接入属另行立项。
