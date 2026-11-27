# 客户端多 clip 支持立项（2026-11-27）

> 立项文档, 非实现文档。铁律: 不动客户端, 改动只进自有目录——本文是产线侧
> 提案, 客户端侧改动待另行立项排期。

## 1. 背景

现契约（client_contract/, crescent-traveler v1 对齐）中 `character_animation.gd`
只读五个字段: `manifest.atlas` / `frames[].region` / `frames[].duration_ms` /
`pivot` / `directions.<d>.idle_frame`。播放模型是**单 clip 单 atlas**:
一次只加载一条 animation.json, 播完 loop 或停在 idle_frame。

class_pipeline 侧已按动作导出独立 clip（motions/idle、attack1、attack2、
death、run + right/walk drop-in）, `character.json.motions` 扩展键已预留全部
路径——客户端忽略未知键, 无副作用。**资产侧已就绪, 客户端侧缺口在播放器**。

## 2. 需求场景（按优先级）

| # | 场景 | 现状缺口 |
|---|------|---------|
| 1 | 移动/静止切换: walk↔idle 无缝过渡 | 只认 directions.walk 的 idle_frame, 真实 idle 在 motions/ 无法被消费 |
| 2 | 攻击连段: attack1→attack2 取消窗口 | 两个 clip 无法在一个播放器内切换, 需重新加载 atlas |
| 3 | 受击打断: hit(3帧) 打断任意动作 | 无 clip 优先级机制, 无播完回落逻辑 |
| 4 | 死亡播放后躺平: death 播完停末帧 | loop=false 的"播完停末帧"行为未实现 |
| 5 | 四方向: up/down 扩展后按朝向选 clip | directions 只有 right(四方向扩展后即有) |

## 3. 契约 schema v2 提案（产线侧, 均为扩展键, 客户端忽略即零破坏）

```jsonc
// character.json 增量
{
  "directions": {                       // 四方向后: right/up/down
    "right": { "manifest": "right/animation.json", "idle_frame": 0 },
    "up":    { "manifest": "up/animation.json",    "idle_frame": 0 }
  },
  "motions": {                          // 扩展键, per direction
    "right": { "idle": "motions/right/idle/animation.json", "attack1": "…" },
    "up":    { "…" }
  },
  "clip_meta": {                        // v2 新增扩展键: 播放器决策用
    "attack1": { "category": "attack", "priority": 10, "loop": false,
                 "cancel_into": ["attack2", "walk"],
                 "active_frames": [3, 5] },      // 打击帧区间(hit 判定)
    "hit":     { "category": "interrupt", "priority": 20, "loop": false,
                 "fallback": "idle" },
    "death":   { "category": "terminal", "priority": 100, "loop": false,
                 "end_behavior": "hold_last" }
  }
}
```

要点:
- **每 clip 自带 loop/fps/duration_ms**, animation.json 本体不动——客户端
  现有单 clip 解析器继续可用, 多 clip 是上层调度。
- `clip_meta` 全部可缺省, 缺省行为 = 单 clip 现状（loop 按文件, 播完停末帧）。
- atlas 仍是**每 clip 一张**(256×256 帧规格不变); 不做合图集, 换 clip = 换
  atlas 引用, 避免一次性载入全部动作纹理。

## 4. 产线侧待办（本项目内, 可先行）

1. 四方向扩展落地后, `export_client_contract.py` 输出 per-direction
   `motions/<dir>/<motion>/` + 各方向 walk drop-in（right/ 布局保持不动,
   up/down 平行新增, 零破坏）。
2. `clip_meta` 生成: 动作类型/loop/priority 由 manifest 静态推导;
   `active_frames` 打击帧人工标注（attack1 f3-f5、attack2 f3-f4 起步）。
3. 契约 QC 增加 clip_meta 完整性校验（每个非空 motion 有 category+priority）。

## 5. 客户端侧待办（另行立项, 不在本项目）

1. 播放器多 clip 状态机: current_clip + priority 抢占 + 播完回落。
2. 过渡策略首版建议**硬切**(hd2d 像素风, 硬切不违和, 免 blend 复杂度);
   blend_ms 字段预留不用。
3. 预加载策略: 常驻 walk+idle atlas, 攻击/死亡按需加载+缓存。

## 6. 验收标准

- [ ] 客户端单 clip 消费路径零变化（旧 character.json 继续可跑）
- [ ] 新 character.json 带 motions+clip_meta, 旧客户端忽略扩展键无警告
- [ ] walk↔idle 切换: 松开方向键回落 idle_frame, 无闪烁
- [ ] attack1 可在 active_frames 后取消进 attack2
- [ ] hit 打断后回落 idle; death 播完躺平不再响应移动
