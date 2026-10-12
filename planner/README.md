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
python3 -m planner.page
```

页面是项目根目录的 `index.html`，没有构建步骤。`python3 -m planner.page` 在本机打开 http://127.0.0.1:8765/ 。也可以直接用浏览器打开这个文件，提交仍发到同一地址。页面把书里的段落当参考，用白话把答案一句一句写出来。

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

本地模型用 `PLANNER_MODEL=local`。权重在项目的 `models/`。书没筛中时，页面和命令行会读这份权重，写一段模型自述。说明在 `planner/model/local/README.md`。输入包和输出约定在 `planner/model/port.md`。

没有来源、没有日期、已经过期，或模型稿里出现筛中清单以外的路径时，回复退回填段模板，不把模型原文交给用户。`data/context/sample-invalid.md` 故意不写来源。

换一份摘要再问同一个问题，书里的路径不变，变的是最小动作和形势对照。

## 复查

命令行默认把记录写在 `data/sessions/current.yaml`。五个验收问题不读、不写它。`--session 名字` 换一份记录。

文件里是主线、入口、上次最小动作、要留下的证据和复查日期。复查日是十四天后。用户岔开时先问要不要换，不把两条线并成一份计划。说「换主线」才换入口，说「不换」就留在原来的入口。

带回记录之后，到了复查日，或话里已经有十四天证据，才打开九十天。没到复查日、也没有十四天证据，仍不写九十天安排。

密码、证件号、住址、病历和他人隐私不写入会话。
