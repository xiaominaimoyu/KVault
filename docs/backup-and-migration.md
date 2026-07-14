# KVault 备份与迁移指南

## 数据结构

KVault 数据存储在以下目录结构中：

```
data/
├── kb.sqlite          # 元数据库
├── chroma_db/         # 向量数据库
├── files/             # 原始文档文件
└── logs/              # 日志文件
```

## 备份

### 手动备份

```bash
# 进入数据目录
cd data

# 创建备份压缩包
zip -r kvault_backup_$(date +%Y%m%d).zip \
  kb.sqlite \
  chroma_db/ \
  files/
```

### 备份内容说明

| 文件/目录 | 说明 | 是否必需 |
|-----------|------|----------|
| kb.sqlite | 文档元数据、标签、分区信息 | 是 |
| chroma_db/ | 向量索引数据 | 是 |
| files/ | 原始上传文档 | 是 |
| logs/ | 日志文件 | 否 |

## 迁移

### 同环境迁移

1. 停止 KVault
2. 复制整个 `data/` 目录到新位置
3. 更新 `config.json` 中的路径配置
4. 启动 KVault

### 跨环境迁移（开发 → 生产）

1. 在开发环境创建备份
2. 将备份文件复制到生产环境
3. 在生产环境解压到数据目录
4. 验证数据完整性

```bash
# 解压到生产环境
unzip kvault_backup_20240101.zip -d /path/to/production/data/
```

## 数据恢复

### 步骤

1. 停止 KVault
2. 删除损坏的数据目录
3. 解压备份文件
4. 启动 KVault
5. 验证文档和检索功能

### 验证命令

```python
# 验证数据库连接
import sqlite3
conn = sqlite3.connect("data/kb.sqlite")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM documents")
print(f"文档数量: {cursor.fetchone()[0]}")
conn.close()
```

## 注意事项

1. **备份时机**: 建议在文档批量导入完成后进行备份
2. **一致性**: 备份前确保无正在进行的索引任务
3. **路径配置**: 迁移后检查 `config.json` 路径是否正确
4. **版本兼容性**: 确保源和目标环境使用相同版本的 KVault
5. **Ollama 模型**: 迁移不包含 Ollama 模型，需单独部署

## 自动备份建议

配置定期备份任务（以 Windows 为例）：

```batch
@echo off
set BACKUP_DIR=C:\KVault\backups
set DATA_DIR=C:\KVault\data

if not exist %BACKUP_DIR% mkdir %BACKUP_DIR%

zip -r %BACKUP_DIR%\kvault_backup_%date:~0,4%%date:~5,2%%date:~8,2%.zip ^
  %DATA_DIR%\kb.sqlite ^
  %DATA_DIR%\chroma_db\ ^
  %DATA_DIR%\files\
```

## 故障恢复

### 场景：数据库损坏

1. 从最近备份恢复 `kb.sqlite`
2. 检查向量数据库是否完整
3. 对损坏的文档执行重新索引

### 场景：向量数据丢失

1. 从备份恢复 `chroma_db/` 目录
2. 如果无备份，对所有文档执行重新索引

### 场景：文档文件丢失

1. 从备份恢复 `files/` 目录
2. 重新上传丢失的文档

## 模型变更处理

KVault 使用 Ollama 提供的 Embedding 模型将文本转换为向量，并存储在 ChromaDB 中。不同模型生成的向量空间、维度通常不兼容，因此**更换 Embedding 模型后必须重建向量索引**，否则检索结果会异常或报错。

### 自动模型名称解析

`core/embedding_service.py` 中的 `EmbeddingService._resolve_model_name()` 会在启动时自动将短名称解析为 Ollama 中存在的完整模型名。例如：

- 配置中写入 `bge-large-zh-v1.5`
- Ollama 实际模型为 `modelscope.cn/Embedding-GGUF/bge-large-zh-v1.5:latest`
- 启动时会自动匹配并修正，无需用户手动填写完整路径

这仅解决**名称匹配**问题，不解决**向量不兼容**问题。

### 安全变更步骤

1. **备份当前数据**

   参考上文「手动备份」章节，完整备份 `data/` 目录。

2. **停止 KVault**

   确保没有导入、重索引等后台任务在运行。

3. **修改模型配置**

   编辑 `config.json` 中的 `embedding_model` 字段，例如：

   ```json
   {
     "embedding_model": "nomic-embed-text"
   }
   ```

   也可以在 GUI 的「设置」对话框中修改，但修改后仍需手动清理向量库。

4. **清理旧向量索引**

   删除或重命名旧的 ChromaDB 目录：

   ```bash
   # 方式一：直接删除（不可逆，请确保已备份）
   rm -rf data/chroma_db

   # 方式二：重命名保留旧索引，便于回滚
   mv data/chroma_db data/chroma_db_backup_$(date +%Y%m%d)
   ```

5. **启动 KVault**

   启动时会自动创建新的空 `chroma_db/` 目录和 `knowledge_base` collection。

6. **重新索引所有文档**

   在 GUI 中：

   - 进入「全部文档」视图
   - 选中所有文档（Ctrl+A）
   - 右键选择「重新索引」

   或在确认安全后编写脚本批量调用 `MetadataManager`/`ingest_document()` 重新导入。

### 验证

重新索引完成后：

1. 查看左侧面板「向量库状态」，确认当前模型名称为新模型。
2. 确认向量总数与文档分块总数一致。
3. 在右侧面板执行一次语义检索，检查结果是否合理。

### 回滚

如果新模型效果不佳，可以回滚到旧模型：

1. 停止 KVault
2. 恢复备份的 `config.json` 和 `chroma_db/` 目录
3. 启动 KVault
4. 验证检索结果与变更前一致

### 注意事项

- **不要混用向量**：同一 `chroma_db/` 目录下不要尝试同时存储两个模型的向量。
- **不要只改配置不清索引**：修改 `embedding_model` 后若未删除旧 `chroma_db/`，检索时会出现维度不匹配或相似度计算错误。
- **重新索引会耗时**：大文档集重新生成嵌入需要一定时间，建议在非工作时段执行。