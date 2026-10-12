# 对话式规划 · 初版

用户用自己的话讲近况。程序在《人生进阶指南》里筛段落，再用筛中的段落填一份四块回复。这一版不接大模型，也不写会话。

语料在 `rensheng/`，只读。索引写到 `data/index/`，可以整份删掉再生成。

## 用法

在项目根目录执行：

```bash
python3 -m planner.cli --rebuild-index
python3 -m planner.cli "我不知道从哪开始，只想重新动一下。今天有半小时。"
python3 -m planner.cli --fixtures
python3 -m unittest planner.tests.test_accept
```

回复里的路径都在 `rensheng/` 下。书里对不上的问题会说明没筛中，并给出最接近的入口标题，不补一份规划。

筛中不足两段、没有十四天证据却要九十天、或话里出现危险念头时，都不往下编计划。危险念头只停在书里写明的求助边界。

## 现在不做

不调用 `planner/model/`，不读 `data/context/`，不往 `data/sessions/` 写记录。这些位置留给后面的阶段。
