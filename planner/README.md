# 对话式规划

用户用自己的话讲近况。程序在《人生进阶指南》里筛段落，再用筛中的段落填一份四块回复。

默认不接大模型，也不写会话。配置了模型，并且有一份合格的形势摘要时，才把最小动作改写成当前条件下的一步，并另附形势对照。建议里的句子仍来自筛中段落。

语料在 `rensheng/`，只读。索引写到 `data/index/`，可以整份删掉再生成。

## 用法

在项目根目录执行：

```bash
python3 -m planner.cli --rebuild-index
python3 -m planner.cli "我不知道从哪开始，只想重新动一下。今天有半小时。"
python3 -m planner.cli --fixtures
python3 -m unittest planner.tests.test_accept planner.tests.test_model
```

回复里的路径都在 `rensheng/` 下。书里对不上的问题会说明没筛中，并给出最接近的入口标题，不补一份规划。

筛中不足两段、没有十四天证据却要九十天、或话里出现危险念头时，都不往下编计划。危险念头只停在书里写明的求助边界。

## 模型

五个验收问题不读形势摘要，始终走填段模板。

要改写最小动作时，配置里只启用一个后端，并指定一份摘要。`data/context/` 里现在有两份合格样本，所以不会自动挑一份。

```bash
export PLANNER_MODEL=api
export PLANNER_API_KEY=你的密钥
export PLANNER_API_MODEL=模型名
python3 -m planner.cli --context data/context/sample-tight.md "我不知道从哪开始，只想重新动一下。今天有半小时。"
```

本地模型用 `PLANNER_MODEL=local`。权重放在项目外，说明在 `planner/model/local/README.md`。输入包和输出约定在 `planner/model/port.md`。

没有来源、没有日期、已经过期，或模型稿里出现筛中清单以外的路径时，回复退回填段模板，不把模型原文交给用户。`data/context/sample-invalid.md` 故意不写来源。

换一份摘要再问同一个问题，书里的路径不变，变的是最小动作和形势对照。

## 现在不做

不往 `data/sessions/` 写记录。复查和十四天记忆还没做。
