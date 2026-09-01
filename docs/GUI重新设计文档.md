# KVault 桌面 GUI 重新设计文档

> **版本**：v1.0
> **日期**：2026-09-01
> **范围**：KVault 桌面端 GUI 视觉与交互的全面重新设计
> **技术基座**：PySide6 (Qt6)，通过 QSS + 自定义 Widget 实现
> **设计语言**：Vault Standard

---

## 一、设计概览

### 1.1 现状诊断

当前 KVault GUI 存在以下视觉与体验问题：

- **原生控件裸奔**：QTableWidget / QTreeWidget / QListWidget 使用 Qt 默认样式，无统一设计语言。
- **色彩零散**：状态色直接硬编码（`#2ecc71` / `#e74c3c` / `#f1c40f`），属于 2014 年 Flat UI 配色，辨识度高但已过时，且与整体无协调关系。
- **信息密度失衡**：左栏堆叠工作区选择器、分区树、标签列表、状态面板四个模块，视觉权重均等，缺乏层次。
- **缺少呼吸感**：控件间距 8-10px 偏紧，内容与边界贴边，长时间使用易疲劳。
- **交互反馈弱**：按钮无 hover/press 态区分，进度反馈仅靠状态栏文字 + 细进度条。
- **无主题系统**：配置项有 `theme: "system"` 字段但未实现，浅色模式是唯一状态。
- **预览体验差**：QTextBrowser 直接渲染 HTML，无代码高亮、无阅读排版优化。

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| **建立设计语言** | 统一色彩、字体、间距、圆角、阴影、动效，形成可复用的 Vault Standard 体系 |
| **深色优先** | 面向开发者/知识工作者的长时间沉浸场景，深色为主、浅色为辅 |
| **信息层次清晰** | 通过视觉权重区分主操作区与辅助区，降低认知负荷 |
| **现代但不花哨** | 参考 Linear / Raycast / Obsidian 的克制美学，不做无意义装饰 |
| **PySide6 可实现** | 所有设计决策须能用 QSS + QPainter 自定义控件落地，不引入 Web 引擎 |

### 1.3 目标用户画像

- 个人开发者 / 研究者 / 写作者，习惯管理大量本地文档
- 重视数据隐私，偏好本地优先
- 长时间使用，需要低视觉疲劳的环境
- 技术素养高，接受密信息布局，但需要清晰的引导

### 1.4 品牌意象

KVault = Knowledge Vault（知识保险库）。

- ** Vaults（保险库）意象**：厚重、可靠、深色金属质感、精密刻度。
- **知识意象**：被照亮的内容、温暖的阅读光、书脊排列。
- 设计语言将这两种意象融合：深色沉稳的容器外壳 + 温暖的琥珀色内容高光。

---

## 二、设计语言：Vault Standard

### 2.1 设计理念

**「深色沉稳容器 + 温暖内容之光」**

整体界面是一个深色的、精密的"保险库"容器；当用户聚焦到内容（文档预览、检索结果、选中文档）时，界面以温暖光色照亮该区域，形成"打开保险柜、照亮内容"的隐喻。

设计三原则：

1. **容器克制、内容突出** — 框架元素（导航、工具栏、边框）保持低饱和深色，把视觉注意力让给内容区。
2. **状态即色彩** — 用色彩编码状态（索引状态、相似度、选中态），而非用色彩装饰。
3. **精密而有呼吸** — 紧凑的信息布局配合充足的内边距和行高，精密但不局促。

### 2.2 色彩系统

#### 2.2.1 深色主题（默认）

**背景层（由深到浅，模拟保险库内壁层级）**

| Token | 色值 | 用途 |
|-------|------|------|
| `--bg-vault` | `#0F1115` | 最底层：窗口背景、空区域 |
| `--bg-surface` | `#161922` | 面板背景：导航栏、工具栏底色 |
| `--bg-raised` | `#1E222C` | 浮起表面：卡片、弹出菜单、表格行 hover |
| `--bg-inset` | `#0C0E13` | 内陷区域：输入框、代码块、状态面板 |

**前景层**

| Token | 色值 | 用途 |
|-------|------|------|
| `--fg-primary` | `#E8EAED` | 主要文字：标题、文档名、正文 |
| `--fg-secondary` | `#9BA1AC` | 次要文字：标签、元信息、占位符 |
| `--fg-muted` | `#5C6370` | 弱化文字：禁用态、提示语 |
| `--fg-faint` | `#3A4049` | 极弱：分割线、边框 |

**品牌与强调色**

| Token | 色值 | 用途 |
|-------|------|------|
| `--accent-primary` | `#2DD4BF` | 主强调：选中态边框、主按钮、激活的分区/标签 |
| `--accent-primary-dim` | `#1A8B7E` | 主强调弱化：hover 底色、未激活指示器 |
| `--accent-warm` | `#F5A623` | 温暖光：内容高亮、检索命中、焦点区域指示 |
| `--accent-warm-dim` | `#B87714` | 温暖光弱化：hover 高亮底 |

**状态色（语义编码）**

| Token | 色值 | 语义 | 对应状态 |
|-------|------|------|----------|
| `--status-success` | `#34D399` | 成功 | indexed |
| `--status-warning` | `#FBBF24` | 进行中 | indexing / pending |
| `--status-error` | `#F87171` | 失败 | failed |
| `--status-info` | `#60A5FA` | 信息 | MCP 连接、同步中 |

> 状态色保持与原版绿/黄/红的语义映射，但降低饱和度使其融入深色环境。

**相似度评分色（检索结果）**

| 区间 | 色值 | 视觉 |
|------|------|------|
| ≥ 0.8 | `#34D399` | 翠绿，高亮命中 |
| 0.5 - 0.79 | `#FBBF24` | 琥珀，部分命中 |
| < 0.5 | `#F87171` | 暖红，低相关 |

#### 2.2.2 浅色主题

| Token | 色值 | 用途 |
|-------|------|------|
| `--bg-vault` | `#F7F8FA` | 窗口背景 |
| `--bg-surface` | `#FFFFFF` | 面板背景 |
| `--bg-raised` | `#F1F3F5` | 卡片、hover |
| `--bg-inset` | `#E8EBEE` | 输入框、内陷 |
| `--fg-primary` | `#1A1D23` | 主文字 |
| `--fg-secondary` | `#5C6370` | 次文字 |
| `--fg-muted` | `#9BA1AC` | 弱文字 |
| `--accent-primary` | `#0D9488` | 主强调（深色版以保证对比度） |
| `--accent-warm` | `#D97706` | 温暖光（深色版） |

#### 2.2.3 主题切换策略

- 默认深色。浅色作为可选。
- 主题通过一个 `theme.qss` 文件统一定义，运行时通过 `QApplication.setStyleSheet()` 切换。
- 配置项 `config.theme` 取值：`dark` / `light` / `system`（system 跟随系统暗色模式）。

### 2.3 字体系统

**字体族**

| 层级 | 字体族 | 说明 |
|------|--------|------|
| 界面 | `"Inter", "Microsoft YaHei UI", "Segoe UI", sans-serif` | 界面文字、按钮、标签 |
| 等宽 | `"JetBrains Mono", "Cascadia Code", "Consolas", monospace` | 文档 ID、路径、代码、数值 |
| 内容 | `"Inter", "Source Han Serif SC", "Noto Serif CJK SC", serif` | 文档预览正文（长文阅读优化） |

> 等宽字用于路径、ID、数值，增强"精密仪器"质感。预览正文使用衬线体提升长文阅读舒适度。

**字号阶梯**

| Token | 字号 | 行高 | 用途 |
|-------|------|------|------|
| `--text-xs` | 11px | 16px | 极小标注、时间戳、提示 |
| `--text-sm` | 13px | 20px | 表格次要列、元信息 |
| `--text-base` | 14px | 22px | 正文、表格主列、按钮 |
| `--text-md` | 15px | 24px | 小标题、面板标题 |
| `--text-lg` | 18px | 28px | 分区标题、对话框标题 |
| `--text-xl` | 22px | 32px | 窗口标题、空状态大字 |

**字重**

| Token | 字重 | 用途 |
|-------|------|------|
| `--font-regular` | 400 | 正文 |
| `--font-medium` | 500 | 表格首列、标签、按钮 |
| `--font-semibold` | 600 | 面板标题、选中态 |
| `--font-bold` | 700 | 窗口标题、空状态标题 |

### 2.4 间距系统

采用 4px 基准网格：

| Token | 值 | 用途 |
|-------|-----|------|
| `--space-1` | 4px | 图标与文字间距、密集行内距 |
| `--space-2` | 8px | 控件间最小间距、列表行间距 |
| `--space-3` | 12px | 卡片内边距、面板间距 |
| `--space-4` | 16px | 面板内边距、区块间距 |
| `--space-5` | 20px | 对话框内边距 |
| `--space-6` | 24px | 大区块间距、空状态 |
| `--space-8` | 32px | 区段间距 |

### 2.5 圆角系统

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius-sm` | 4px | 输入框、小按钮、标签 pill |
| `--radius-md` | 6px | 按钮、表格单元格内框 |
| `--radius-lg` | 8px | 卡片、面板、对话框 |
| `--radius-full` | 9999px | 圆形指示器、头像、状态点 |

### 2.6 阴影与层级

深色主题中阴影不可见，改用边框 + 背景色差表达层级：

| 层级 | 表达方式 |
|------|----------|
| L0 基底 | `--bg-vault` 纯色 |
| L1 表面 | `--bg-surface` + 1px `--fg-faint` 右/下边框 |
| L2 浮起 | `--bg-raised` + 1px `--fg-faint` 全边框 + 2px 上偏移微亮边框 |
| L3 弹出 | `--bg-raised` + 1px 半透明强调色边框 + QSS `border-radius: 8px` |

浅色主题额外使用投影：`0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)`。

### 2.7 图标系统

- 采用 **Lucide** 图标集（线性、2px 描边、圆角线帽），风格与深色精密界面契合。
- 图标统一 16px（工具栏） / 14px（行内） / 20px（空状态）。
- 颜色继承前景色，选中/激活态使用 `--accent-primary`。

**各功能图标映射**

| 功能 | 图标 | 功能 | 图标 |
|------|------|------|------|
| 导入文档 | `upload` | 设置 | `settings` |
| 全局搜索 | `search` | 日志 | `file-text` |
| 新建工作区 | `folder-plus` | 删除 | `trash-2` |
| 分区 | `folder` | 标签 | `tag` |
| 刷新 | `refresh-cw` | 打开文件 | `external-link` |
| 重新索引 | `refresh-cw` | 移动分区 | `folder-input` |
| 编辑标签 | `tags` | 检索 | `search` |
| 数据库 | `database` | 工作区 | `layers` |

---

## 三、布局架构

### 3.1 整体结构

保留三栏布局骨架（导航 + 列表 + 详情），但重新分配权重与间距：

```
┌─────────────────────────────────────────────────────────────────┐
│  顶部导航栏 (56px)                                                │
│  [Logo] KVault   [全局搜索 ........]   [工作区▾] [导入] [设置] [☰] │
├──────────┬───────────────────────────┬──────────────────────────┤
│          │                           │                          │
│ 左侧     │  文档列表区                │  详情面板                 │
│ 导航     │  (卡片网格 / 列表)          │  (预览 + 检索)            │
│ (260px)  │  (自适应)                  │  (480px+)                │
│          │                           │                          │
├──────────┴───────────────────────────┴──────────────────────────┤
│  底部状态栏 (32px)                                                │
│  [● 就绪]  [12 文档 · 340 块]  ────────  [进度条]  [Ollama ✓]    │
└─────────────────────────────────────────────────────────────────┘
```

**三栏尺寸**：左导航 260px（可折叠至 48px 图标栏）、文档列表自适应、详情面板最小 480px。

**间距**：三栏之间无间隙，以 1px `--fg-faint` 分割线分隔；面板内边距 16px。

### 3.2 左侧导航面板重新设计

当前左栏堆叠四块（工作区、分区、标签、状态），视觉均等。重新设计后按使用频率分层：

**结构（从上到下）**

1. **工作区切换器**（顶部，常驻显眼）
   - 下拉选择器 + 当前工作区名，展示文档数徽章。
   - "新建"和"删除"折叠为右侧小图标按钮。

2. **分区树**（主体，最大高度）
   - 树形展示，每行：图标 + 名称 + 文档数 pill。
   - 选中行使用 `--accent-primary-dim` 左边框 3px + 背景微亮。
   - 右键菜单保持原有功能。

3. **标签区**（中部，可滚动）
   - 改为标签 pill 网格而非列表，每个 pill：`#标签名 · 3`。
   - 选中 pill 高亮 `--accent-primary` 边框。
   - 取消筛选时点击已选 pill 或点击"全部"pill。

4. **状态摘要**（底部，折叠式）
   - 默认折叠为一行摘要：`12 文档 · 340 块 · bge-large-zh`。
   - 点击展开为 4 行详细统计面板。
   - 不再使用 QTextBrowser，改用自定义 InfoCard 组件。

**视觉处理**

- 面板背景 `--bg-surface`，右侧 1px 分割线。
- 各区块标题用 `--text-sm` `--font-medium` `--fg-secondary`，上方 8px 间距。
- 分区/标签行高 32px，hover 态 `--bg-raised`。

### 3.3 文档列表区重新设计

当前使用 QTableWidget 七列表格。重新设计提供**双视图**切换：

#### 3.3.1 列表视图（默认）

保留表格结构但全面美化：

- 表头：`--bg-surface` 背景、`--text-sm` `--fg-secondary` `--font-medium`、行高 36px、底部 1px 分割线。
- 数据行：行高 40px、`--bg-vault` 背景、hover `--bg-raised`、选中 `--accent-primary-dim` 左 3px 边框 + 微亮背景。
- 状态列：用**圆点指示器**（8px 圆形）替代纯色文字，圆点右侧跟 `--text-sm` 状态文字。
- 格式列：用**格式徽章**（圆角矩形，背景 `--bg-inset`，`--text-xs` 等宽字），如 `PDF` `DOCX` `MD`。
- 块数/大小列：`--text-sm` 等宽字、右对齐、`--fg-secondary`。
- 分隔：行间无网格线，改为底部 1px `--fg-faint` 微分隔。
- 文档名列：`--text-base` `--fg-primary`，失败状态文字色 `--status-error`。

#### 3.3.2 卡片网格视图（可选）

适合视觉浏览场景：

- 每张卡片 220px 宽，高度自适应。
- 卡片内容：顶部格式徽章 + 文件名（2 行截断）+ 底部状态点 + 元信息行。
- 卡片背景 `--bg-surface`、1px 边框 `--fg-faint`、`--radius-lg`、hover 时边框变 `--accent-primary`。
- 选中卡片：边框 `--accent-primary` 2px + 背景 `--accent-primary-dim` 10%。

#### 3.3.3 视图切换

- 列表/卡片切换按钮组放在文档列表区右上角（列表标题栏右侧）。
- 记忆用户选择到 config。

### 3.4 详情面板重新设计

当前右栏垂直拆分为预览 + 检索。重新设计为**标签页**结构：

```
┌──────────────────────────────────┐
│ [预览] [检索] [元数据]            │  ← Tab 栏
├──────────────────────────────────┤
│                                  │
│  内容区（根据 Tab 切换）           │
│                                  │
└──────────────────────────────────┘
```

#### 3.4.1 预览标签页

- 顶部文档信息卡：文件名（`--text-lg` `--font-semibold`）+ 元信息行（格式徽章、大小、状态、块数、分区、标签）。
- 内容区：衬线体 `--text-base`、行高 1.8、最大宽度 720px 居中、`--fg-primary`。
- 文本块概览：每个块用折叠卡片展示，标题"块 N"，内容截断 2 行，点击展开。
- 检索命中块：高亮 `--accent-warm-dim` 背景 + 左 3px `--accent-warm` 边框。
- 空状态："选择文档查看预览" + 文档图标。

#### 3.4.2 检索标签页

- 搜索框：大输入框（高 40px）+ Top-K 选择器 + 检索按钮，一行布局。
- 输入框聚焦时 1px `--accent-primary` 边框 + 微光。
- 结果列表：每条结果为卡片，含文档名 + 块号 + 相似度分数条 + 内容预览（3 行截断）。
- 相似度分数条：水平进度条，颜色按区间映射，宽度与分数成正比。
- 点击结果：切换到预览标签页并定位命中块。

#### 3.4.3 元数据标签页（新增）

- 以键值表形式展示：文档 ID（等宽）、存储路径（等宽）、原始路径、导入时间、更新时间、分区、标签、错误信息。
- 路径支持点击复制。
- 失败文档的错误信息用 `--status-error` 背景卡片突出。

### 3.5 顶部导航栏重新设计

从工具栏改为结构化导航栏：

```
┌─────────────────────────────────────────────────────────────────┐
│ [▣] KVault   [🔍 全局搜索 ...........................]   [工作区▾] │
│                                          [导入] [设置] [日志] [☰]│
└─────────────────────────────────────────────────────────────────┘
```

- 高度 56px、背景 `--bg-surface`、底部 1px 分割线。
- 左侧：应用 Logo（16px 方形图标 + "KVault" 文字 `--text-md` `--font-semibold`）。
- 中间：全局搜索框，宽度自适应（min 320px），圆角 `--radius-md`，左侧搜索图标。
- 右侧操作区：工作区下拉、导入按钮（主按钮样式）、设置/日志/菜单（图标按钮）。
- 导入按钮：`--accent-primary` 背景、白色文字、`--radius-md`、hover 提亮。

### 3.6 底部状态栏重新设计

```
┌─────────────────────────────────────────────────────────────────┐
│ ● 就绪    12 文档 · 340 块 · bge-large-zh           ▓▓▓▓░ 60%  │
└─────────────────────────────────────────────────────────────────┘
```

- 高度 32px、背景 `--bg-surface`、顶部 1px 分割线。
- 左侧：状态指示点（8px 圆形，颜色映射状态）+ 状态文字 `--text-sm` `--fg-secondary`。
- 中间：统计摘要 `--text-xs` `--fg-muted` 等宽字。
- 右侧：进度条（仅导入/重索引时显示）+ Ollama 状态指示。
- 进度条：高度 4px、`--bg-inset` 轨道、`--accent-primary` 填充、圆角。

---

## 四、对话框与覆盖层设计

### 4.1 设置对话框

从当前 QFormLayout 堆叠改为**分类标签页**：

```
┌─────────────────────────────────────────┐
│ 设置                              [✕]    │
├─────────────────────────────────────────┤
│ [常规] [检索] [模型] [MCP] [外观]        │
├─────────────────────────────────────────┤
│                                         │
│  (当前 Tab 的设置项)                      │
│                                         │
├─────────────────────────────────────────┤
│              [取消]  [保存]              │
└─────────────────────────────────────────┘
```

- 窗口 560 x 480px、`--bg-surface`、`--radius-lg`。
- Tab 栏在顶部，`--text-sm`，选中 tab 底部 2px `--accent-primary`。
- 表单项之间 16px 间距，标签 `--fg-secondary` 右对齐。
- 保存按钮使用主按钮样式。
- 切分参数变更提示：用 `--accent-warm-dim` 背景的信息条，带 `info` 图标。

### 4.2 启动检查对话框

保留现有卡片式设计但统一到设计语言：

- 背景 `--bg-surface`、`--radius-lg`。
- 每项检查结果卡片：`--bg-raised` 背景、`--radius-md`、12px 内边距。
- 通过/失败图标：圆形 24px 背景，✓ 用 `--status-success`、✗ 用 `--status-error`。
- 建议文字：`--text-sm` `--fg-secondary` 斜体。
- 按钮：重试用主按钮、跳过用次要按钮（`--bg-raised` 背景 `--fg-primary` 文字）。

### 4.3 增量更新对话框

- 差异清单用三色标签区分：新增（`--status-success`）、修改（`--status-warning`）、删除（`--status-error`）。
- 每行：标签 pill + 文件路径（等宽字）。
- 进度阶段用步骤指示器：扫描 → 确认 → 执行 → 完成。

### 4.4 模型切换对话框

- 步骤指示器：备份 → 重建 → 校验 → 完成（或回滚）。
- 状态实时更新，每步骤完成显示 ✓。
- 失败回滚提示用 `--status-error` 背景信息条。

### 4.5 右键菜单

统一菜单样式：

- 背景 `--bg-raised`、`--radius-md`、8px 内边距、1px `--fg-faint` 边框。
- 菜单项：行高 32px、`--text-sm`、左侧 8px 图标空间、hover `--accent-primary-dim` 背景。
- 分割线：1px `--fg-faint`、上下 4px margin。
- 危险操作（删除）：hover `--status-error` 10% 背景 + `--status-error` 文字。

### 4.6 消息对话框（确认/警告/错误）

替代默认 QMessageBox：

- `--bg-surface`、`--radius-lg`、24px 内边距。
- 图标 32px 圆形背景：info=`--status-info`、warning=`--status-warning`、error=`--status-error`。
- 标题 `--text-lg` `--font-semibold`、正文 `--text-base` `--fg-secondary`。
- 按钮区右对齐，主操作用主按钮，取消用次要按钮。

---

## 五、交互模式

### 5.1 选中态

- 文档列表行选中：左 3px `--accent-primary` 边框 + 背景 `--accent-primary-dim` 15%。
- 分区/标签选中：背景 `--accent-primary-dim` 15% + 文字 `--accent-primary`。
- 卡片选中：2px `--accent-primary` 边框。

### 5.2 Hover 态

- 列表行：背景 `--bg-raised`。
- 按钮：主按钮提亮（`--accent-primary` → 更亮 10%）；次要按钮 `--bg-raised`。
- 分区树节点：背景 `--bg-raised`。

### 5.3 焦点态（键盘可达性）

- 输入框/按钮：1px `--accent-primary` 边框 + 2px 外发光（半透明 `--accent-primary` 30%）。
- 列表项：虚线轮廓 `--accent-primary`。

### 5.4 拖拽导入

- 新增：支持拖拽文件到窗口任意位置导入。
- 拖入时全窗口覆盖半透明遮罩（`--accent-primary` 10%）+ 中心大字"释放导入"。

### 5.5 批量操作

- 多选文档时，列表底部浮现操作工具条：`已选 3 项 · [移动] [标签] [重索引] [删除]`。
- 工具条 `--bg-raised`、`--radius-md`、浮动在列表底部、带阴影。

### 5.6 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+I` | 导入文档 |
| `Ctrl+F` | 聚焦全局搜索 |
| `Ctrl+K` | 聚焦语义检索 |
| `Ctrl+S` | 设置 |
| `Ctrl+R` | 刷新状态 |
| `Delete` | 删除选中文档（需确认） |
| `Esc` | 清除选中 / 关闭对话框 |
| `Ctrl+1/2/3` | 切换详情面板标签页 |

---

## 六、动效规范

### 6.1 原则

- 动效服务于状态反馈和空间认知，不用于装饰。
- 时长偏短（150-250ms），缓动使用 `ease-out`。
- 支持 `prefers-reduced-motion`（通过配置项 `config.reduce_motion` 禁用所有动画）。

### 6.2 具体动效

| 场景 | 时长 | 缓动 | 效果 |
|------|------|------|------|
| 面板 Tab 切换 | 150ms | ease-out | 内容区淡入 |
| 列表行 hover | 100ms | ease-out | 背景色过渡 |
| 选中态变化 | 150ms | ease-out | 边框 + 背景过渡 |
| 进度条更新 | 200ms | ease-out | 宽度过渡 |
| 拖拽遮罩 | 200ms | ease-out | 透明度淡入 |
| 对话框出现 | 200ms | ease-out | 缩放 0.96→1 + 淡入 |
| 空状态出现 | 300ms | ease-out | 图标 + 文字上移淡入 |

> PySide6 中通过 `QPropertyAnimation` 实现，对 QWidget 的 `windowOpacity`、`pos`、自定义属性做插值。

---

## 七、空状态与加载状态

### 7.1 空状态设计

每个区域在无数据时显示引导：

| 区域 | 图标 | 标题 | 副标题 | 行动 |
|------|------|------|--------|------|
| 文档列表 | `file-search` | "还没有文档" | "拖拽文件到此处，或点击导入" | [导入文档] 按钮 |
| 检索结果 | `search-x` | "未找到相关结果" | "试试调整关键词或增大 Top-K" | — |
| 预览面板 | `file-text` | "选择文档查看预览" | "从左侧列表选择一个文档" | — |
| 分区树 | `folder` | "还没有分区" | "右键新建分区来组织文档" | — |
| 标签区 | `tag` | "还没有标签" | "在文档右键菜单中添加标签" | — |

- 空状态居中显示，图标 48px `--fg-muted`、标题 `--text-lg` `--fg-primary`、副标题 `--text-sm` `--fg-secondary`。
- 间距：图标与标题 16px、标题与副标题 8px。

### 7.2 加载状态

| 场景 | 表现 |
|------|------|
| 导入中 | 底部进度条 + 状态栏文字"正在索引：filename (60%)" |
| 检索中 | 检索按钮变为 loading 态（图标旋转 + 禁用）+ 输入框右侧 spinner |
| 重索引中 | 同导入态 |
| 状态面板刷新 | 面板内容区短暂 dim 50% + 居中 spinner |

---

## 八、组件清单与样式规范

### 8.1 按钮

| 类型 | 样式 |
|------|------|
| 主按钮 | `--accent-primary` 背景、白色文字、`--radius-md`、高 32px、hover 提亮 10% |
| 次要按钮 | `--bg-raised` 背景、`--fg-primary` 文字、1px `--fg-faint` 边框 |
| 图标按钮 | 32x32px、透明背景、hover `--bg-raised`、图标 16px |
| 危险按钮 | `--status-error` 背景、白色文字 |

### 8.2 输入框

- 高 32px、`--bg-inset` 背景、1px `--fg-faint` 边框、`--radius-sm`。
- 聚焦：1px `--accent-primary` 边框 + 2px 外发光。
- Placeholder：`--fg-muted` 斜体。

### 8.3 下拉选择器

- 样式同输入框，右侧下拉箭头图标。
- 弹出列表用自定义 QListView，`--bg-raised` 背景、`--radius-md`、每项 32px 行高。

### 8.4 标签 Pill

- `--radius-full`、内边距 4px 10px、`--text-xs`、`--bg-inset` 背景。
- 选中：`--accent-primary` 15% 背景 + `--accent-primary` 文字。
- hover：`--bg-raised`。

### 8.5 格式徽章

- `--radius-sm`、内边距 2px 6px、`--text-xs` 等宽字、`--bg-inset` 背景、`--fg-secondary` 文字。

### 8.6 状态指示点

- 8px 圆形、颜色映射状态。
- 闪烁动画：indexing 状态 1.5s 循环透明度脉动（除非 reduce_motion）。

### 8.7 分数条

- 高 4px、`--bg-inset` 轨道、`--radius-full`。
- 填充宽度 = score * 100%，颜色按区间映射。

### 8.8 卡片

- `--bg-surface`、1px `--fg-faint` 边框、`--radius-lg`、16px 内边距。
- hover：边框 `--accent-primary`。
- 选中：边框 `--accent-primary` 2px + 背景微亮。

### 8.9 树节点

- 行高 32px、`--text-sm`。
- 展开/折叠箭头：12px 三角形，`--fg-muted`。
- 选中：背景 `--accent-primary-dim` 15% + 左 3px `--accent-primary` 边框。

---

## 九、PySide6 实现指引

### 9.1 QSS 架构

```
gui/styles/
├── theme_dark.qss      # 深色主题全局样式
├── theme_light.qss     # 浅色主题全局样式
├── variables.py        # 色彩/间距 Token 定义（Python 常量）
└── apply.py            # 主题应用逻辑
```

- `variables.py` 定义所有 Token 为 Python 常量，QSS 文件中通过字符串模板替换引用。
- `apply.py` 提供 `apply_theme(app, theme_name)` 函数，读取对应 QSS 并 `setStyleSheet`。

### 9.2 自定义 Widget 清单

需要继承自定义的控件：

| Widget | 父类 | 说明 |
|--------|------|------|
| `StatusDot` | QWidget | 8px 圆形状态指示器，支持脉动动画 |
| `FormatBadge` | QLabel | 格式徽章，自动大写 + 等宽字 |
| `ScoreBar` | QWidget | 相似度分数条 |
| `DocCard` | QFrame | 卡片网格视图中的文档卡片 |
| `TagPill` | QPushButton | 可选中的标签 pill |
| `EmptyState` | QWidget | 空状态组件（图标 + 标题 + 副标题 + 按钮） |
| `StepIndicator` | QWidget | 步骤指示器（模型切换/增量更新） |
| `FloatingActionBar` | QFrame | 批量操作浮动工具条 |

### 9.3 主窗口重构

将 `main_window.py` 的巨型类拆分到独立模块：

```
gui/
├── main_window.py          # 组装 + 信号路由
├── styles/                 # QSS + Token
├── widgets/                # 自定义控件
├── panels/
│   ├── nav_panel.py        # 左侧导航（重构自 _build_nav_panel）
│   ├── doc_list_panel.py   # 文档列表（重构自 doc_table 逻辑）
│   ├── detail_panel.py     # 详情 Tab 面板
│   ├── preview_tab.py     # 预览标签页
│   ├── search_tab.py      # 检索标签页
│   └── metadata_tab.py    # 元数据标签页
├── dialogs/
│   ├── settings_dialog.py  # 设置（标签页化重构）
│   ├── startup_dialog.py   # 启动检查（美化）
│   ├── incremental_dialog.py
│   └── model_switch_dialog.py
└── workers/                # 保留现有
```

### 9.4 图标集成

- 安装 `lucide-icons` 的 SVG 资源，或使用 `qtpy` 的 SVG 渲染。
- 图标通过 `QIcon` 加载 SVG，颜色通过 SVG fill 属性动态着色（深色/浅色 + 状态色）。
- 资源路径：`gui/styles/icons/{name}.svg`。

### 9.5 字体集成

- Inter 和 JetBrains Mono 可打包到 `gui/styles/fonts/`，通过 `QFontDatabase.addApplicationFont()` 注册。
- 衬线体使用系统已安装的 Source Han Serif / Noto Serif CJK SC，不打包。

### 9.6 主题应用示例

```python
# gui/styles/apply.py
from gui.styles.variables import DARK_TOKENS, LIGHT_TOKENS

def apply_theme(app, theme: str = "dark"):
    tokens = DARK_TOKENS if theme == "dark" else LIGHT_TOKENS
    qss = _load_qss(f"theme_{theme}.qss")
    qss = _interpolate(qss, tokens)
    app.setStyleSheet(qss)
```

---

## 十、迁移计划

### 10.1 分阶段实施

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| P1 | 搭建 QSS 架构 + Token 系统 + 深色主题全局样式 | 高 |
| P2 | 重构顶部导航栏 + 底部状态栏 | 高 |
| P3 | 美化左侧导航面板（分区树、标签 pill、状态摘要） | 高 |
| P4 | 文档列表表格样式 + 状态点 + 格式徽章 | 高 |
| P5 | 详情面板 Tab 化 + 预览/检索/元数据标签页 | 中 |
| P6 | 设置对话框分类标签页 + 各对话框美化 | 中 |
| P7 | 自定义 Widget（EmptyState / ScoreBar / StepIndicator 等） | 中 |
| P8 | 卡片网格视图 + 拖拽导入 + 批量操作浮动条 | 低 |
| P9 | 动效集成 + 键盘快捷键 + 浅色主题 | 低 |
| P10 | 图标系统 + 字体打包 + 最终打磨 | 低 |

### 10.2 兼容性约束

- 不改动 `core/` 层任何代码，GUI 重设计仅涉及 `gui/` 目录。
- 保持所有现有信号槽连接逻辑不变，仅替换视图层。
- `config.theme` 字段已有，直接复用。
- `MainWindow` 对外暴露的方法名和信号保持不变，确保 `main.py` 入口不需改动。

### 10.3 验收标准

- [ ] 深色主题在 1080p / 1440p / 4K 显示下无像素错位。
- [ ] 所有交互有 hover / focus / disabled 态。
- [ ] 空状态在所有区域正确显示。
- [ ] 进度反馈在导入/检索/重索引时正确展示。
- [ ] 键盘可完成所有核心操作（Tab 导航 + 快捷键）。
- [ ] 浅色主题对比度通过 WCAG AA（正文 ≥ 4.5:1）。
- [ ] `main.py` 入口零改动即可启动新界面。

---

## 十一、设计 Token 速查表

> 以下为实现时直接引用的完整 Token 清单。

### 色彩 — 深色

```python
TOKENS_DARK = {
    # 背景
    "bg-vault": "#0F1115",
    "bg-surface": "#161922",
    "bg-raised": "#1E222C",
    "bg-inset": "#0C0E13",
    # 前景
    "fg-primary": "#E8EAED",
    "fg-secondary": "#9BA1AC",
    "fg-muted": "#5C6370",
    "fg-faint": "#3A4049",
    # 强调
    "accent-primary": "#2DD4BF",
    "accent-primary-dim": "#1A8B7E",
    "accent-warm": "#F5A623",
    "accent-warm-dim": "#B87714",
    # 状态
    "status-success": "#34D399",
    "status-warning": "#FBBF24",
    "status-error": "#F87171",
    "status-info": "#60A5FA",
}
```

### 色彩 — 浅色

```python
TOKENS_LIGHT = {
    "bg-vault": "#F7F8FA",
    "bg-surface": "#FFFFFF",
    "bg-raised": "#F1F3F5",
    "bg-inset": "#E8EBEE",
    "fg-primary": "#1A1D23",
    "fg-secondary": "#5C6370",
    "fg-muted": "#9BA1AC",
    "fg-faint": "#D1D5DB",
    "accent-primary": "#0D9488",
    "accent-primary-dim": "#5EEAD4",
    "accent-warm": "#D97706",
    "accent-warm-dim": "#FDE68A",
    "status-success": "#059669",
    "status-warning": "#D97706",
    "status-error": "#DC2626",
    "status-info": "#2563EB",
}
```

### 间距与圆角

```python
SPACING = {"1": 4, "2": 8, "3": 12, "4": 16, "5": 20, "6": 24, "8": 32}
RADIUS = {"sm": 4, "md": 6, "lg": 8, "full": 9999}
```

### 字体

```python
FONT_UI = '"Inter", "Microsoft YaHei UI", "Segoe UI", sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", monospace'
FONT_CONTENT = '"Inter", "Source Han Serif SC", "Noto Serif CJK SC", serif'

TEXT_SIZES = {"xs": 11, "sm": 13, "base": 14, "md": 15, "lg": 18, "xl": 22}
TEXT_WEIGHTS = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700}
```

---

*本文档为 KVault 桌面 GUI 重新设计的完整规范，后续实现以此为准。*
