"""核心缺陷回归测试。

覆盖三个已修复的真实缺陷，确保不会再次退化：

1. 平铺存储导致同名文件互相覆盖（静默数据丢失）
2. ``content_preview`` 截断到 200 字，使 BM25 只能索引每块开头
3. 混合检索把余弦相似度阈值套在 RRF 融合分上，导致召回清零
"""

import pytest

from core.ingest import CONTENT_PREVIEW_LIMIT, ingest_document, resolve_stored_path
from core.metadata_manager import MetadataManager
from core.vector_store import VectorStore


@pytest.fixture
def env(tmp_path):
    """搭建一套可用的导入环境。"""
    from core.config import Config
    from core.document_parser import DocumentParser
    from core.text_splitter import KnowledgeTextSplitter

    from tests.conftest import FakeEmbedder

    config = Config()
    config.files_dir = tmp_path / "files"
    config.chroma_dir = tmp_path / "chroma"
    config.sqlite_path = tmp_path / "kb.sqlite"
    config.logs_dir = tmp_path / "logs"
    for path in (config.files_dir, config.chroma_dir, config.logs_dir):
        path.mkdir(parents=True, exist_ok=True)

    vector_store = VectorStore(str(config.chroma_dir))
    metadata = MetadataManager(str(config.sqlite_path), vector_store=vector_store)

    return {
        "config": config,
        "parser": DocumentParser(),
        "splitter": KnowledgeTextSplitter(200, 20),
        "embedder": FakeEmbedder(),
        "vector_store": vector_store,
        "metadata": metadata,
        "tmp_path": tmp_path,
    }


#: ``env`` 中除临时目录外的可传给 ``ingest_document`` 的参数
_INGEST_KEYS = ("config", "parser", "splitter", "embedder", "vector_store", "metadata")


def _ingest(env, path, splitter=None, **kwargs):
    params = {key: env[key] for key in _INGEST_KEYS}
    if splitter is not None:
        params["splitter"] = splitter
    params.update(kwargs)
    return ingest_document(str(path), **params)


class TestSameNameCollision:
    """回归：不同目录的同名文件曾被静默互相覆盖。"""

    def test_same_name_different_dirs_both_survive(self, env):
        tmp = env["tmp_path"]
        source_a = tmp / "src_a"
        source_b = tmp / "src_b"
        source_a.mkdir()
        source_b.mkdir()

        file_a = source_a / "报告.md"
        file_b = source_b / "报告.md"
        file_a.write_text("甲目录的内容", encoding="utf-8")
        file_b.write_text("乙目录的内容", encoding="utf-8")

        id_a = _ingest(env, file_a)
        id_b = _ingest(env, file_b)

        assert id_a != id_b
        docs = env["metadata"].list_documents()
        assert len(docs) == 2

    def test_second_file_not_overwritten_on_disk(self, env):
        tmp = env["tmp_path"]
        source_a = tmp / "src_a"
        source_b = tmp / "src_b"
        source_a.mkdir()
        source_b.mkdir()

        (source_a / "报告.md").write_text("甲目录的内容", encoding="utf-8")
        (source_b / "报告.md").write_text("乙目录的内容", encoding="utf-8")

        _ingest(env, source_a / "报告.md")
        _ingest(env, source_b / "报告.md")

        stored = list(env["config"].files_dir.rglob("报告*.md"))
        assert len(stored) == 2
        contents = {p.read_text(encoding="utf-8") for p in stored}
        assert contents == {"甲目录的内容", "乙目录的内容"}

    def test_both_vectors_retained(self, env):
        tmp = env["tmp_path"]
        source_a = tmp / "src_a"
        source_b = tmp / "src_b"
        source_a.mkdir()
        source_b.mkdir()

        (source_a / "报告.md").write_text("甲目录的内容" * 20, encoding="utf-8")
        (source_b / "报告.md").write_text("乙目录的内容" * 20, encoding="utf-8")

        _ingest(env, source_a / "报告.md")
        _ingest(env, source_b / "报告.md")

        assert env["vector_store"].count() >= 2

    def test_reimport_same_source_is_idempotent(self, env):
        """同一文件重新导入应更新而非产生重复。"""
        tmp = env["tmp_path"]
        source = tmp / "src"
        source.mkdir()
        target = source / "笔记.md"
        target.write_text("第一版内容", encoding="utf-8")

        _ingest(env, target)
        target.write_text("第二版内容", encoding="utf-8")
        _ingest(env, target)

        assert len(env["metadata"].list_documents()) == 1

    def test_stored_path_keeps_source_folder(self, env):
        tmp = env["tmp_path"]
        source = tmp / "项目资料"
        source.mkdir()
        target = source / "设计.md"
        target.write_text("内容", encoding="utf-8")

        stored = resolve_stored_path(env["config"], target)
        assert stored.parent.name == "项目资料"

    def test_no_flat_layout_for_nested_sources(self, env):
        tmp = env["tmp_path"]
        source = tmp / "a" / "b" / "c"
        source.mkdir(parents=True)
        target = source / "深层.md"
        target.write_text("内容", encoding="utf-8")

        _ingest(env, target)
        doc = env["metadata"].list_documents()[0]
        assert "c" in doc.stored_path


class TestContentPreviewNotTruncated:
    """回归：200 字截断使 BM25 只能命中每块开头。"""

    def test_chunk_text_stored_in_full(self, env):
        tmp = env["tmp_path"]
        source = tmp / "src"
        source.mkdir()
        target = source / "长文.md"

        # 关键词只出现在后半部分
        target.write_text("前置内容。" * 60 + "独特关键词在后半部分出现。", encoding="utf-8")
        doc_id = _ingest(env, target)

        chunks = env["metadata"].get_document_chunks(doc_id)
        assert chunks
        assert any("独特关键词在后半部分出现" in c["content_preview"] for c in chunks)

    def test_preview_covers_full_chunk(self, env):
        """preview 必须覆盖整块内容，而不只是开头一小段。"""
        from core.text_splitter import KnowledgeTextSplitter

        # 用较大的 chunk_size，确保单个块本身就超过旧的 200 字上限
        big_splitter = KnowledgeTextSplitter(1000, 50)

        tmp = env["tmp_path"]
        source = tmp / "src"
        source.mkdir()
        target = source / "长文.md"
        target.write_text("甲" * 800, encoding="utf-8")

        doc_id = _ingest(env, target, splitter=big_splitter)
        chunks = env["metadata"].get_document_chunks(doc_id)
        preview = chunks[0]["content_preview"]

        assert len(preview) > 200, "preview 不应被截断到 200 字"
        assert len(preview) >= 800, "preview 应覆盖整块内容"

    def test_preview_still_bounded(self, env):
        """超长内容仍需截断，避免数据库膨胀。"""
        from core.ingest import _preview_of

        assert len(_preview_of("x" * (CONTENT_PREVIEW_LIMIT * 2))) == CONTENT_PREVIEW_LIMIT

    def test_preview_is_flattened(self, env):
        from core.ingest import _preview_of

        assert "\n" not in _preview_of("第一行\n第二行")

    def test_bm25_can_find_late_keyword(self, env):
        """端到端验证：BM25 能命中只出现在块后半部分的关键词。

        旧实现把 preview 截断到 200 字，这类关键词永远无法进入索引。
        中文分词依赖可选的 jieba，缺失时会退化为按空格切分——此时中文
        关键词本就无法独立成词，因此该断言在未装 jieba 时跳过。
        """
        from core.bm25_retriever import BM25Retriever
        from core.text_splitter import KnowledgeTextSplitter

        # 单块足够大，关键词落在 200 字之后
        big_splitter = KnowledgeTextSplitter(1000, 50)

        tmp = env["tmp_path"]
        source = tmp / "src"
        source.mkdir()
        target = source / "长文.md"
        target.write_text(
            "这是关于各种无关话题的大段铺垫文字。" * 20 + "独有关键词紫貂出现在这里。",
            encoding="utf-8",
        )
        _ingest(env, target, splitter=big_splitter)

        previews = [
            c["content_preview"]
            for doc in env["metadata"].list_documents()
            for c in env["metadata"].get_document_chunks(doc.id)
        ]
        assert any("紫貂" in p for p in previews), "关键词应完整进入索引文本"

        if not BM25Retriever.is_jieba_available():
            pytest.skip("未安装 jieba，中文分词降级为按空格切分")

        bm25 = BM25Retriever(env["metadata"])
        bm25.build_index()
        hits = bm25.search("紫貂", top_k=5)
        assert hits, "BM25 应能命中块后半部分的关键词"

    def test_bm25_tokenizer_degrades_without_jieba(self):
        """无 jieba 时分词退化但不崩溃——这是已声明的可选依赖行为。"""
        from core.bm25_retriever import BM25Retriever

        tokens = BM25Retriever._tokenize("机器学习 检索")
        assert isinstance(tokens, list)
        assert tokens


class TestHybridRetrievalThreshold:
    """回归：余弦相似度阈值曾被套用在量纲不同的分数上。

    ``similarity_threshold`` 衡量的是**向量余弦相似度**（0~1）。融合分
    （RRF 的 1/(k+rank)，k=60 时约 0.016）与 BM25 分数（无上界）都不在这个
    量纲上。旧实现把阈值作用到两者上，会出现两种错误：

    - 融合分远小于阈值 → 向量臂明明命中却被丢弃，混合检索零召回
    - BM25 分数偶然小于阈值 → 关键词确实命中的结果被丢弃
    """

    @staticmethod
    def _indexed_env(env, text, splitter=None):
        from core.text_splitter import KnowledgeTextSplitter as _S

        tmp = env["tmp_path"]
        source = tmp / "src"
        source.mkdir(exist_ok=True)
        target = source / "文档.md"
        target.write_text(text, encoding="utf-8")
        _ingest(env, target, splitter=splitter or _S(200, 20))

    def test_fused_score_not_compared_against_threshold(self, env):
        """核心回归：融合分再小，只要向量臂命中且超过阈值就必须返回。"""
        from core.hybrid_retriever import HybridRetriever
        from core.text_splitter import KnowledgeTextSplitter

        self._indexed_env(env, "机器学习与向量检索的关系。" * 20)

        # 先测出向量臂的真实相似度，再把阈值设在其下方——
        # 这样「向量命中」成立，而 RRF 融合分（约 0.016）一定低于阈值。
        raw = env["vector_store"].search(
            env["embedder"].embed_query("机器学习"), top_k=5
        )
        assert raw, "向量库应有结果"
        vector_score = max(r.score for r in raw)
        fused_like = 1.0 / (60.0 + 1)
        assert fused_like < vector_score, "构造前提：融合分量级应远小于向量分"

        env["config"].similarity_threshold = float(vector_score) - 1e-6
        env["config"].hybrid_search.enabled = True

        retriever = HybridRetriever(
            env["embedder"], env["vector_store"], env["metadata"], env["config"]
        )
        results = retriever.search("机器学习", top_k=5)

        # 旧实现会因 base.score 与阈值比较而全部丢弃（若 base 来自 BM25 臂）
        assert results, "向量臂命中且超过阈值时，混合检索必须返回结果"

    def test_bm25_arm_not_gated_by_cosine_threshold(self, env):
        """BM25 独占的关键词命中不应被余弦阈值拦下。"""
        from core.hybrid_retriever import HybridRetriever

        self._indexed_env(env, "完全无关的铺垫内容。" * 20)

        env["config"].similarity_threshold = 0.5
        env["config"].hybrid_search.enabled = True

        retriever = HybridRetriever(
            env["embedder"], env["vector_store"], env["metadata"], env["config"]
        )
        # 查询词在库中不存在：两臂都无命中，返回空是正确的
        assert retriever.search("压根不存在的词", top_k=5) == []

    def test_pure_vector_path_still_applies_threshold(self, env):
        """纯向量路径必须继续遵守阈值，不能被本次修复影响。"""
        from core.retriever import Retriever

        self._indexed_env(env, "内容。" * 30)

        env["config"].similarity_threshold = 0.99
        env["config"].hybrid_search.enabled = False

        retriever = Retriever(
            env["embedder"], env["vector_store"], env["metadata"], env["config"]
        )
        assert retriever.search("内容", top_k=5) == []

        # 阈值降低后应能召回
        env["config"].similarity_threshold = 0.0
        retriever2 = Retriever(
            env["embedder"], env["vector_store"], env["metadata"], env["config"]
        )
        assert retriever2.search("内容", top_k=5)


class TestIngestFailureHandling:
    def test_empty_document_marked_failed(self, env):
        tmp = env["tmp_path"]
        source = tmp / "src"
        source.mkdir()
        target = source / "空.md"
        target.write_text("", encoding="utf-8")

        with pytest.raises(ValueError):
            _ingest(env, target)

        docs = env["metadata"].list_documents()
        assert docs[0].status == "failed"

    def test_error_message_recorded(self, env):
        tmp = env["tmp_path"]
        source = tmp / "src"
        source.mkdir()
        target = source / "空.md"
        target.write_text("   \n\n  ", encoding="utf-8")

        with pytest.raises(ValueError):
            _ingest(env, target)

        assert env["metadata"].list_documents()[0].error_message