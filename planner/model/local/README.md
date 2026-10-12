# 本地小模型

权重放在项目外面的目录，不提交，也不放进 `rensheng/`。

程序不读取权重里的内容。它只确认 `PLANNER_LOCAL_WEIGHTS` 指向项目外一块已经存在的路径，然后把和 API 相同的输入包发给本机服务。

本机服务要事先启动，并使用那份权重。接口需要兼容 OpenAI 的 `chat/completions`，例如 llama.cpp 的 server，或 Ollama 的兼容地址。

```bash
export PLANNER_MODEL=local
export PLANNER_LOCAL_WEIGHTS=/本机路径/权重
export PLANNER_LOCAL_URL=http://127.0.0.1:8080/v1
export PLANNER_LOCAL_MODEL=服务里的模型名
python3 -m planner.cli --context data/context/sample-open.md "我不知道从哪开始，只想重新动一下。今天有半小时。"
```

`PLANNER_MODEL=local` 时不再走 API。密钥不要写进这个目录。
